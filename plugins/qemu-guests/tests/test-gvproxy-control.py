"""Controller contracts that do not require a VM or native helper."""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import signal
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("control", ROOT / "scripts/gvproxy-control.py")
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)
from resource_ownership import signals


class ControllerTests(unittest.TestCase):
    def test_mapping_validation(self):
        self.assertEqual([(20000, 80), (65535, 65535)],
                         control.read_mappings(io.StringIO("20000:80\n65535:65535\n")))
        for value in ("0:80", "1:65536", "２０００:80", "20000:80\n20000:81", "1:2:3"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                control.read_mappings(io.StringIO(value))

    def test_reuses_connection_and_refuses_redirect_without_retry(self):
        connection = Mock()
        responses = [SimpleNamespace(status=status, read=lambda: b"") for status in (200, 302)]
        connection.getresponse.side_effect = responses
        with patch.object(control.http.client, "HTTPConnection", return_value=connection) as factory:
            with self.assertRaisesRegex(RuntimeError, "HTTP 302"):
                control.register_mappings(19201, [(20000, 80), (20001, 81), (20002, 82)])
        factory.assert_called_once_with("127.0.0.1", 19201, timeout=5)
        self.assertEqual(2, connection.request.call_count)
        connection.close.assert_called_once()

    def test_batch_deadline_aborts_before_request(self):
        connection = Mock()
        with patch.object(control.http.client, "HTTPConnection", return_value=connection), \
                patch.object(control.time, "monotonic", side_effect=[0, 31]):
            with self.assertRaises(TimeoutError):
                control.register_mappings(19201, [(20000, 80)])
        connection.request.assert_not_called()
        connection.close.assert_called_once()

    @unittest.skipIf(os.name == "nt", "Unix resource limits")
    def test_listener_limits_raise_soft_only_and_refuse_small_hard_limit(self):
        import resource
        with patch.object(resource, "getrlimit", return_value=(1024, 65536)), \
                patch.object(resource, "setrlimit") as setter:
            control.listener_budget(10005)
            setter.assert_called_once_with(resource.RLIMIT_NOFILE, (10261, 65536))
        with patch.object(resource, "getrlimit", return_value=(1024, 1024)), \
                patch.object(resource, "setrlimit") as setter:
            with self.assertRaisesRegex(RuntimeError, "hard limit"):
                control.listener_budget(10005)
            setter.assert_not_called()


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.directory)
        self.state = self.root / 'helper.pid'
        self.args = SimpleNamespace(configure=False, state=str(self.state),
            log=str(self.root / 'helper.log'), binary='synthetic-helper', transport=12345, api=12346)
        self.handlers = {number: signal.getsignal(number) for number in signals()}
        self.addCleanup(self.restore_handlers)
        for number in self.handlers:
            signal.signal(number, lambda n, _f: sys.exit(128 + n))
        self.exit_handlers = {number: signal.getsignal(number) for number in signals()}
        self.enterContext(patch.object(control.socket, 'socket'))
        self.enterContext(patch.object(control, 'listener_budget'))

    def restore_handlers(self):
        for number, handler in self.handlers.items():
            signal.signal(number, handler)

    def cancel(self, number=signal.SIGTERM):
        signal.getsignal(number)(number, None)

    def test_cancel_at_creation_return_joins_real_child_before_removing_record(self):
        original = subprocess.Popen
        # No scheduler timing: invoke the installed handler after real process
        # creation but before returning its handle to the production assignment.
        for number in signals():
            with self.subTest(signal=number):
                children = []
                def spawn(*_args, **_kwargs):
                    child = original([sys.executable, '-c', 'import time; time.sleep(60)'],
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    children.append(child)
                    self.cancel(number)
                    return child
                try:
                    with patch.object(control.subprocess, 'Popen', side_effect=spawn):
                        with self.assertRaises(SystemExit) as error:
                            control.start(self.args)
                    self.assertEqual(error.exception.code, 128 + number)
                    self.assertEqual(len(children), 1)
                    self.assertIsNotNone(children[0].poll())
                    self.assertFalse(self.state.exists())
                    self.assertEqual(signal.getsignal(number), self.exit_handlers[number])
                finally:
                    for child in children:
                        if child.poll() is None:
                            child.kill()
                        child.wait(timeout=5)

    def test_definitive_creation_failure_cleans_only_own_reservation(self):
        with patch.object(control.subprocess, 'Popen', side_effect=OSError('synthetic creation failure')):
            with self.assertRaises(OSError):
                control.start(self.args)
        self.assertFalse(self.state.exists())

    def test_creation_failure_with_pending_cancel_removes_reservation(self):
        def failed(*_args, **_kwargs):
            self.cancel()
            raise OSError('synthetic creation failure')
        with patch.object(control.subprocess, 'Popen', side_effect=failed):
            with self.assertRaises(SystemExit) as error:
                control.start(self.args)
        self.assertEqual(error.exception.code, 128 + signal.SIGTERM)
        self.assertFalse(self.state.exists())

    def test_second_cancel_during_join_finishes_cleanup_before_delivery(self):
        child = Mock()
        child.poll.return_value = None
        def spawn(*_args, **_kwargs):
            self.cancel()
            return child
        def joined(**kwargs):
            self.assertEqual(kwargs, {'timeout': 10})
            self.assertTrue(self.state.exists())
            self.cancel(signal.SIGINT)
            return 0
        child.wait.side_effect = joined
        with patch.object(control.subprocess, 'Popen', side_effect=spawn):
            with self.assertRaises(SystemExit) as error:
                control.start(self.args)
        self.assertEqual(error.exception.code, 128 + signal.SIGINT)
        child.kill.assert_called_once()
        child.wait.assert_called_once_with(timeout=10)
        self.assertFalse(self.state.exists())

    def test_unconfirmed_child_exit_retains_pending_evidence(self):
        for failure in ('kill', 'join'):
            with self.subTest(failure=failure):
                child = Mock()
                child.poll.return_value = None
                if failure == 'kill':
                    child.kill.side_effect = OSError('synthetic termination failure')
                else:
                    child.wait.side_effect = subprocess.TimeoutExpired('synthetic-helper', 10)
                def spawn(*_args, **_kwargs):
                    self.cancel()
                    return child
                with patch.object(control.subprocess, 'Popen', side_effect=spawn):
                    with self.assertRaises((OSError, subprocess.TimeoutExpired)):
                        control.start(self.args)
                self.assertTrue(json.loads(self.state.read_text())['pending'])
                with self.assertRaisesRegex(RuntimeError, 'Incomplete'):
                    control.stop(self.state)
                self.state.unlink()  # Only synthetic state; no real process exists.

    def test_reservation_write_failure_rolls_back_only_new_file(self):
        with patch.object(control.json, 'dump', side_effect=OSError('synthetic reservation failure')):
            with self.assertRaises(OSError):
                control.start(self.args)
        self.assertFalse(self.state.exists())
        self.state.write_text('preexisting unknown ownership')
        with self.assertRaisesRegex(RuntimeError, 'Existing'):
            control.start(self.args)
        self.assertEqual(self.state.read_text(), 'preexisting unknown ownership')

    def test_control_guard_creation_cancel_releases_only_own_guard(self):
        original = Path.mkdir
        guard = Path(str(self.state) + '.control.lock')
        def mkdir(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path == guard:
                self.cancel()
            return result
        argv = ['gvproxy-control.py', 'start', '--state', str(self.state)]
        with patch.object(sys, 'argv', argv), patch.object(Path, 'mkdir', mkdir), \
             patch.object(control, 'dispatch') as dispatch:
            with self.assertRaises(SystemExit):
                control.main()
        dispatch.assert_not_called()
        self.assertFalse(guard.exists())
        guard.mkdir()
        with patch.object(sys, 'argv', argv), self.assertRaises(FileExistsError):
            control.main()
        self.assertTrue(guard.exists())


if __name__ == "__main__":
    unittest.main()
