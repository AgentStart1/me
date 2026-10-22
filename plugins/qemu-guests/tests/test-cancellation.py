"""Cooperative cancellation checkpoints and owned, bounded SSH waits; no VMs."""
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from resource_ownership import Cancelled, defer_cancellation
from test_command_tree import TestCommandTree
from test_cancellation import CancellationRequest, CancellationPhase, cancellation_context, current_cancellation
from test_cli_lifecycle import CliSignalScope
from test_environment_owner import TestEnvironmentOwner, OwnerState
from test_environment_owner import CleanupUncertain
from test_guest_transport import GuestTransport, TransportCleanupError


class CooperativeCancellationTests(unittest.TestCase):
    def test_real_owned_host_command_is_cancelled_and_joined_without_async_exception(self):
        with CliSignalScope() as cli:
            owner = TestEnvironmentOwner(cancellation=cli.cancellation)
            tree = TestCommandTree()
            children = []
            def work():
                with owner:
                    owner.callback(tree.stop)
                    with patch('signal.signal', wraps=signal.signal) as install:
                        child = tree.start([sys.executable, '-c', 'import time; time.sleep(30)'],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        install.assert_not_called()
                    children.append(child)
                    timer = threading.Timer(.1, lambda: signal.raise_signal(signal.SIGINT))
                    timer.start()
                    try:
                        return owner.wait(child)
                    finally:
                        timer.cancel()
                        timer.join(timeout=5)
            outcome = cli.execute(work)
            self.assertEqual(outcome.error.status, 130)
            self.assertEqual(len(children), 1)
            self.assertIsNotNone(children[0].poll())
            self.assertIs(owner.state, OwnerState.RELEASED)
            self.assertEqual(owner.cleanup_failures, ())

    def test_nested_handoffs_defer_checkpoints_without_changing_handlers(self):
        with CliSignalScope() as cli:
            with patch('signal.signal', wraps=signal.signal) as install:
                with defer_cancellation(), defer_cancellation():
                    signal.raise_signal(signal.SIGTERM)
                    cli.cancellation.checkpoint()
                install.assert_not_called()
                self.assertIsNone(cli.cancellation.accepted)
                with self.assertRaises(Cancelled) as raised:
                    cli.cancellation.checkpoint()
                self.assertEqual(raised.exception.status, 143)

    def test_context_restores_outer_request_on_exception(self):
        outer, inner = CancellationRequest(), CancellationRequest()
        with cancellation_context(outer):
            with self.assertRaises(ValueError):
                with cancellation_context(inner):
                    self.assertIs(current_cancellation(), inner)
                    raise ValueError('synthetic')
            self.assertIs(current_cancellation(), outer)
        self.assertIsNone(current_cancellation())

    def test_first_accepted_cancellation_survives_later_requests(self):
        request = CancellationRequest()
        request.request(signal.SIGTERM)
        with self.assertRaises(Cancelled) as raised:
            request.checkpoint()
        request.request(signal.SIGINT)
        self.assertIs(request.begin_cleanup(raised.exception), raised.exception)
        with request.shield():
            request.checkpoint()
        self.assertEqual(request.accepted.status, 143)

    def test_explicit_execution_interrupt_keeps_identity_before_cleanup(self):
        for original in (Cancelled(15), KeyboardInterrupt(), SystemExit(7)):
            with self.subTest(kind=type(original).__name__):
                request = CancellationRequest()
                request.request(signal.SIGINT)
                self.assertIs(request.begin_cleanup(original), original)
                request.request(signal.SIGTERM)
                with request.shield():
                    request.checkpoint()
                self.assertIs(request.accepted, original)

    def test_cleanup_shield_does_not_disable_cancellation_in_other_workers(self):
        request = CancellationRequest()
        original = Cancelled(15)
        request.begin_cleanup(original)
        observed = []
        def worker():
            try:
                request.checkpoint()
            except Cancelled as error:
                observed.append(error)
        with request.shield():
            request.checkpoint()
            thread = threading.Thread(target=worker)
            thread.start()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(observed, [original])

    def test_first_request_after_cleanup_begins_has_no_execution_effect(self):
        request = CancellationRequest()
        self.assertIsNone(request.begin_cleanup())
        request.request(signal.SIGINT)
        request.checkpoint()
        self.assertIsNone(request.accepted)
        self.assertIs(request.phase, CancellationPhase.DRAINING)
        request.finish()
        request.request(signal.SIGTERM)
        request.checkpoint()
        self.assertIs(request.phase, CancellationPhase.FINISHED)

    def test_pending_request_before_cleanup_is_not_lost(self):
        request = CancellationRequest()
        request.request(signal.SIGTERM)
        with cancellation_context(request), tempfile.TemporaryDirectory() as directory:
            owner = TestEnvironmentOwner(directory, cancellation=request)
            closed = Mock()
            with self.assertRaises(Cancelled) as raised:
                with owner:
                    owner.callback(closed)
            closed.assert_called_once()
            self.assertEqual(raised.exception.status, 143)
            self.assertIs(owner.state, OwnerState.RELEASED)
            self.assertFalse((Path(directory) / 'test-environment.lock').exists())

    def test_explicit_cleanup_interrupt_drains_remaining_resources_and_retains_lock(self):
        with CliSignalScope() as cli, tempfile.TemporaryDirectory() as directory:
            owner = TestEnvironmentOwner(directory, cancellation=cli.cancellation)
            remaining = Mock(side_effect=OSError('private cleanup'))
            original = Cancelled(15)
            def interrupt():
                signal.raise_signal(signal.SIGINT)
                raise original
            def work():
                with owner:
                    owner.callback(remaining)
                    owner.callback(interrupt)
            result = cli.execute(work)
            self.assertIs(result.error, original)
            remaining.assert_called_once()
            self.assertTrue(owner.lease_retained)
            self.assertIs(owner.state, OwnerState.RETAINED)
            self.assertTrue(any(isinstance(item, OSError) for item in result.error.__cause__.failures))

    def test_partial_owner_entry_observes_cancellation_and_keeps_failed_lease(self):
        with CliSignalScope() as cli, tempfile.TemporaryDirectory() as directory:
            owner = TestEnvironmentOwner(directory, cancellation=cli.cancellation)
            def publish(*args):
                signal.raise_signal(signal.SIGTERM)
                raise OSError('private metadata')
            def work():
                with owner:
                    self.fail('Failed acquisition must not run work')
            with patch('test_environment_owner.write_record', side_effect=publish):
                outcome = cli.execute(work)
            self.assertEqual(outcome.error.status, 143)
            self.assertTrue(owner.lease_retained)
            self.assertTrue(owner.cleanup_failures)

    def test_uncertain_incoming_error_is_retained_when_cancellation_already_accepted(self):
        with CliSignalScope() as cli, tempfile.TemporaryDirectory() as directory:
            owner = TestEnvironmentOwner(directory, cancellation=cli.cancellation)
            closed = Mock()
            original = Cancelled(15)
            def work():
                with owner:
                    owner.callback(closed)
                    cli.cancellation.observe(original)
                    raise CleanupUncertain('synthetic uncertain child stop')
            outcome = cli.execute(work)
            self.assertIs(outcome.error, original)
            closed.assert_called_once()
            self.assertTrue(owner.lease_retained)
            self.assertTrue(any(isinstance(item, CleanupUncertain) for item in owner.cleanup_failures))

    def test_context_suppression_cannot_swallow_accepted_cancellation(self):
        with CliSignalScope() as cli, tempfile.TemporaryDirectory() as directory:
            owner = TestEnvironmentOwner(directory)
            manager = Mock()
            manager.__enter__ = Mock()
            manager.__exit__ = Mock(return_value=True)
            def work():
                with owner:
                    owner.enter_context(manager)
                    signal.raise_signal(signal.SIGTERM)
                    owner.checkpoint()
            outcome = cli.execute(work)
            self.assertEqual(outcome.error.status, 143)
            manager.__exit__.assert_called_once()
            self.assertIs(owner.cancellation, cli.cancellation)
            self.assertIs(owner.state, OwnerState.RELEASED)


class CooperativeTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.request = CancellationRequest()
        self.context = cancellation_context(self.request)
        self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)
        self.transport = GuestTransport({'ssh_user': 'fixture', 'access_key': 'fixture-key',
                                         'ssh_port': 2222}, self.temp.name)
        self.child = Mock()
        self.child.poll.return_value = 0
        self.child.returncode = 0
        self.child.stdin = None
        self.child.stdout = None
        self.child.stderr = None

    def test_communicate_retries_wait_without_restarting_or_resending_payload(self):
        self.child.communicate.side_effect = [subprocess.TimeoutExpired('fixture', .1), (b'OK', b'')]
        with patch('test_guest_transport.subprocess.Popen', return_value=self.child) as start:
            self.assertEqual(self.transport.run(['fixture'], stdin_data=b'payload'), b'OK')
        start.assert_called_once()
        self.assertEqual(self.child.communicate.call_args_list[0].kwargs['input'], b'payload')
        self.assertIsNone(self.child.communicate.call_args_list[1].kwargs['input'])
        self.assertEqual(self.transport.children, [])

    def test_real_local_transport_child_receives_input_once_across_wait_slices(self):
        payload = b'synthetic-payload' * 1024
        script = ('import sys,time; data=sys.stdin.buffer.read(); time.sleep(.2); '
                  'sys.stdout.buffer.write(str(len(data)).encode())')
        result = self.transport.run([sys.executable, '-c', script], stdin_data=payload, timeout=5)
        self.assertEqual(int(result), len(payload))
        self.assertEqual(self.transport.children, [])

    def test_request_during_communicate_stops_owned_child_and_preserves_cancellation(self):
        def communicate(**options):
            self.request.request(signal.SIGTERM)
            raise subprocess.TimeoutExpired('fixture', options['timeout'])
        self.child.communicate.side_effect = communicate
        self.child.poll.return_value = None
        with patch('test_guest_transport.subprocess.Popen', return_value=self.child) as start:
            with self.assertRaises(Cancelled) as raised:
                self.transport.run(['fixture'])
        self.assertEqual(raised.exception.status, 143)
        start.assert_called_once()
        self.child.communicate.assert_called_once()
        self.child.terminate.assert_called_once()
        self.assertEqual(self.transport.children, [])

    def test_failed_cancelled_child_stop_retains_handle_and_lease(self):
        self.child.poll.return_value = None
        original = Cancelled(15)
        with tempfile.TemporaryDirectory() as directory:
            owner = TestEnvironmentOwner(directory, cancellation=self.request)
            def communicate(**options):
                raise original
            self.child.communicate.side_effect = communicate
            self.child.terminate.side_effect = OSError('private child')
            with patch('test_guest_transport.subprocess.Popen', return_value=self.child):
                with self.assertRaises(Cancelled) as raised:
                    with owner:
                        owner.callback(self.transport.close)
                        self.transport.run(['fixture'])
            self.assertIs(raised.exception, original)
            self.assertEqual(self.transport.children, [self.child])
            self.assertTrue(owner.lease_retained)
            self.assertTrue(owner.cleanup_failures)

    def test_total_transport_timeout_stops_child_without_rerunning_command(self):
        with patch('test_guest_transport.subprocess.Popen', return_value=self.child) as start, \
                patch('test_guest_transport.time.monotonic', side_effect=[0, 2]):
            with self.assertRaises(subprocess.TimeoutExpired):
                self.transport.run(['fixture'], timeout=1)
        start.assert_called_once()
        self.child.communicate.assert_not_called()
        self.assertEqual(self.transport.children, [])

    def test_request_during_forward_readiness_leaves_child_owned_for_cleanup(self):
        self.child.poll.return_value = None
        def pending(_):
            self.request.request(signal.SIGTERM)
        with patch('test_guest_transport.subprocess.Popen', return_value=self.child) as start, \
                patch('test_guest_transport.time.sleep', side_effect=pending):
            with self.assertRaises(Cancelled):
                self.transport.forward(['-L', '127.0.0.1:4000:127.0.0.1:4000'])
        start.assert_called_once()
        self.assertEqual(self.transport.children, [self.child])
        self.request.begin_cleanup(self.request.accepted)
        self.transport.close()
        self.child.terminate.assert_called_once()


if __name__ == '__main__':
    unittest.main()
