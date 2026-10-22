"""Concurrent worker reports, main-thread commits and lease decisions; no VMs."""
from contextlib import redirect_stderr, redirect_stdout
import http.client
import io
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_cancellation as cancellation
from resource_ownership import Cancelled
from test_cancellation import CancellationRequest, CancellationPhase, WorkerDrainError
from test_cli_lifecycle import CliSignalScope
from test_environment_owner import TestEnvironmentOwner, OwnerState, CleanupUncertain
from test_guest_transport import GuestTransport
from test_appium_proxy import AppiumProxy
from test_cleanup_diagnostics import report_cleanup
import test_environment_owner as owner_module


class WorkerProtocolTests(unittest.TestCase):
    def run_worker(self, operation):
        results, errors = [], []
        def work():
            try:
                results.append(operation())
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=work)
        thread.start()
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        return results, errors

    def test_pending_worker_checkpoint_cannot_construct_or_replace_main_outcome(self):
        request = CancellationRequest()
        request.request(signal.SIGINT)
        ready, release = threading.Event(), threading.Event()
        worker_constructions, errors = [], []
        class ProbeCancelled(Cancelled):
            def __init__(self, number):
                if threading.current_thread() is not threading.main_thread():
                    worker_constructions.append(number)
                    ready.set()
                    if not release.wait(5):
                        raise AssertionError('Worker construction did not resume')
                super().__init__(number)
        def worker():
            try:
                request.checkpoint()
            except BaseException as error:
                errors.append(error)
            finally:
                ready.set()
        with patch.object(cancellation, 'Cancelled', ProbeCancelled):
            thread = threading.Thread(target=worker)
            thread.start()
            try:
                self.assertTrue(ready.wait(5))
                original = SystemExit(7)
                self.assertIs(request.begin_cleanup(original), original)
            finally:
                release.set()
                thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(worker_constructions, [])
        self.assertEqual(errors, [])
        self.assertIs(request.accepted, original)
        self.assertEqual(request.accepted.code, 7)

    def test_worker_observation_is_queued_until_main_commits_it(self):
        request = CancellationRequest()
        original = SystemExit(7)
        def worker():
            request.observe(original)
            self.assertIsNone(request.accepted)
        _, errors = self.run_worker(worker)
        self.assertEqual(errors, [])
        self.assertIsNone(request.accepted)
        request.collect()
        self.assertIs(request.accepted, original)

    def test_main_primary_interrupt_has_priority_over_uncommitted_worker_event(self):
        for already_committed in (False, True):
            with self.subTest(already_committed=already_committed):
                request = CancellationRequest()
                observed = Cancelled(15)
                primary = SystemExit(7)
                _, errors = self.run_worker(lambda: request.observe(observed))
                self.assertEqual(errors, [])
                if already_committed:
                    request.collect()
                expected = observed if already_committed else primary
                self.assertIs(request.begin_cleanup(primary), expected)
                request.collect()
                self.assertIs(request.accepted, expected)

    def test_only_main_can_collect_or_change_phase(self):
        for method in ('collect', 'begin_cleanup', 'finish', 'seal_workers'):
            with self.subTest(method=method):
                request = CancellationRequest()
                _, errors = self.run_worker(getattr(request, method))
                self.assertEqual(len(errors), 1)
                self.assertIsInstance(errors[0], RuntimeError)
                self.assertIs(request.phase, CancellationPhase.RUNNING)
                self.assertIsNone(request.accepted)

    def test_worker_cannot_publish_cli_terminal_snapshot(self):
        with CliSignalScope() as cli:
            owner = TestEnvironmentOwner(cancellation=cli.cancellation)
            cli.execute(lambda: 23)
            _, errors = self.run_worker(lambda: cli.result(owner))
            self.assertIsInstance(errors[0], RuntimeError)
            self.assertIsNone(cli._result)
            self.assertEqual(cli.result(owner).status, 23)

    def test_concurrent_failure_producers_are_all_preserved(self):
        request = CancellationRequest()
        gate = threading.Barrier(3)
        originals = [OSError('synthetic first'), PermissionError('synthetic second')]
        errors = []
        def worker(original):
            try:
                with request.worker():
                    gate.wait(timeout=5)
                    request.report_cleanup(original)
            except BaseException as error:
                errors.append(error)
        threads = [threading.Thread(target=worker, args=(original,)) for original in originals]
        for thread in threads:
            thread.start()
        gate.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        request.begin_cleanup()
        request.seal_workers()
        self.assertEqual({id(error) for error in request.cleanup_failures}, {id(error) for error in originals})

    def test_worker_cannot_release_or_retain_main_owned_lease(self):
        with CliSignalScope() as cli, tempfile.TemporaryDirectory() as directory:
            owner = TestEnvironmentOwner(directory, cancellation=cli.cancellation)
            def work():
                with owner:
                    before = (Path(directory) / 'test-environment.lock/owner.json').read_bytes()
                    for action in (owner.retain, lambda: owner.__exit__(None, None, None),
                                   lambda: owner.cleanup(Mock()), lambda: owner.callback(Mock())):
                        _, errors = self.run_worker(action)
                        self.assertEqual(len(errors), 1)
                        self.assertIsInstance(errors[0], RuntimeError)
                        self.assertEqual((Path(directory) / 'test-environment.lock/owner.json').read_bytes(), before)
                        self.assertIs(owner.state, OwnerState.ACTIVE)
                return 23
            outcome = cli.execute(work)
            self.assertEqual(outcome.status, 23)
            self.assertIs(owner.state, OwnerState.RELEASED)

    def test_failure_reports_survive_conversion_and_are_not_consumed_destructively(self):
        request = CancellationRequest()
        original = OSError('synthetic private stop')
        def worker():
            with request.worker():
                request.report_cleanup(original)
                request.report_cleanup(original)
                raise RuntimeError('HTTP converts this response')
        _, errors = self.run_worker(worker)
        self.assertIsInstance(errors[0], RuntimeError)
        self.assertEqual(request.cleanup_failures, ())
        request.collect()
        self.assertEqual(request.cleanup_failures, (original,))
        request.collect()
        request.seal_workers()
        self.assertEqual(request.cleanup_failures, (original,))

    def test_nested_worker_operations_finish_before_sealing(self):
        request = CancellationRequest()
        entered, leave = threading.Event(), threading.Event()
        failures = []
        def worker():
            try:
                with request.worker(), request.worker():
                    entered.set()
                    if not leave.wait(5):
                        raise AssertionError('Worker did not resume')
                    request.report_cleanup(OSError('synthetic cleanup'))
            except BaseException as error:
                failures.append(error)
        thread = threading.Thread(target=worker)
        thread.start()
        try:
            self.assertTrue(entered.wait(5))
            request.begin_cleanup()
            with self.assertRaises(WorkerDrainError):
                request.seal_workers()
        finally:
            leave.set()
            thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])
        request.seal_workers()
        self.assertEqual(len(request.cleanup_failures), 1)

    def test_closed_admission_prevents_new_resource_work(self):
        request = CancellationRequest()
        request.begin_cleanup()
        started = Mock()
        def worker():
            with request.worker():
                started()
        _, errors = self.run_worker(worker)
        self.assertIsInstance(errors[0], RuntimeError)
        started.assert_not_called()
        request.seal_workers()

    def test_acceptance_fence_ignores_requests_enqueued_after_it(self):
        for first in (None, signal.SIGTERM):
            with self.subTest(first=first):
                request = CancellationRequest()
                real = request._events
                class QueueWithLateRequest:
                    def put(self, event):
                        real.put(event)
                        if not isinstance(event, cancellation.WorkerEvent):
                            real.put(cancellation.WorkerEvent(cancellation.WorkerEventKind.REQUEST, signal.SIGINT))
                    def get(self):
                        return real.get()
                if first is not None:
                    request.request(first)
                request._events = QueueWithLateRequest()
                accepted = request.begin_cleanup()
                request.collect()
                if first is None:
                    self.assertIsNone(accepted)
                    self.assertIsNone(request.accepted)
                else:
                    self.assertEqual(accepted.status, 143)
                    self.assertIs(request.accepted, accepted)

    def test_completed_snapshot_does_not_accept_late_worker_interruptions(self):
        request = CancellationRequest()
        request.begin_cleanup()
        request.seal_workers()
        request.finish()
        _, errors = self.run_worker(lambda: request.observe(SystemExit(7)))
        self.assertEqual(errors, [])
        request.collect()
        self.assertIsNone(request.accepted)
        self.assertIs(request.phase, CancellationPhase.FINISHED)

    def test_unjoined_worker_prevents_lock_release_and_reports_uncertainty(self):
        with CliSignalScope() as cli, tempfile.TemporaryDirectory() as directory:
            owner = TestEnvironmentOwner(directory, cancellation=cli.cancellation)
            entered, release = threading.Event(), threading.Event()
            errors = []
            def worker():
                try:
                    with cli.cancellation.worker():
                        entered.set()
                        if not release.wait(5):
                            raise AssertionError('Worker did not resume')
                except BaseException as error:
                    errors.append(error)
            thread = threading.Thread(target=worker)
            def work():
                with owner:
                    thread.start()
                    self.assertTrue(entered.wait(5))
                return 23
            try:
                cli.execute(work)
                result = cli.result(owner)
                self.assertEqual(result.status, 1)
                self.assertTrue(result.cleanup.lease_retained)
                self.assertIn(('unconfirmed', 1), result.cleanup.categories)
                self.assertTrue((Path(directory) / 'test-environment.lock').exists())
            finally:
                release.set()
                thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])

    def test_worker_failure_and_failed_retention_publication_keep_original_cancel(self):
        with CliSignalScope() as cli, tempfile.TemporaryDirectory() as directory:
            owner = TestEnvironmentOwner(directory, cancellation=cli.cancellation)
            original = Cancelled(15)
            failure = OSError('synthetic-private-worker')
            closed = [Mock(), Mock()]
            write = owner_module.write_record
            def publish(path, record):
                self.assertIs(threading.current_thread(), threading.main_thread())
                if record['phase'] == 'cleanup-uncertain':
                    raise PermissionError('synthetic-private-publish')
                return write(path, record)
            def worker():
                with cli.cancellation.worker():
                    cli.cancellation.report_cleanup(failure)
            def work():
                with owner:
                    for close in closed:
                        owner.callback(close)
                    _, errors = self.run_worker(worker)
                    self.assertEqual(errors, [])
                    raise original
            with patch.object(owner_module, 'write_record', side_effect=publish):
                outcome = cli.execute(work)
            self.assertIs(outcome.error, original)
            result = cli.result(owner)
            self.assertEqual(result.status, 143)
            self.assertTrue(result.cleanup.lease_retained)
            self.assertIn(('io', 1), result.cleanup.categories)
            self.assertIn(('permission', 1), result.cleanup.categories)
            for close in closed:
                close.assert_called_once()
            self.assertTrue((Path(directory) / 'test-environment.lock').exists())
            output = io.StringIO()
            report_cleanup(result.cleanup, output)
            self.assertNotIn('synthetic-private', output.getvalue())


class WorkerHttpOwnershipTests(unittest.TestCase):
    def test_http_control_interrupt_is_reported_without_raw_worker_traceback(self):
        for original, status in ((KeyboardInterrupt(), 130), (SystemExit(7), 7)):
            with self.subTest(kind=type(original).__name__), tempfile.TemporaryDirectory() as directory, CliSignalScope() as cli:
                original.__cause__ = OSError('synthetic-private-cause')
                owner = TestEnvironmentOwner(directory, cancellation=cli.cancellation)
                proxy = AppiumProxy('http://127.0.0.1:1', None,
                                   {'launch': {}, 'cleanup_roots': []}, Path(directory))
                proxy.launch = Mock()
                proxy.launch.prepare.side_effect = original
                replies = []
                def work():
                    with owner:
                        owner.callback(proxy.close)
                        proxy.start()
                        connection = http.client.HTTPConnection('127.0.0.1', proxy.server.server_port, timeout=5)
                        try:
                            connection.request('POST', '/session', b'{"desiredCapabilities":{}}')
                            response = connection.getresponse()
                            replies.append((response.status, response.read()))
                        finally:
                            connection.close()
                        return 23
                with patch('threading.excepthook') as unhandled:
                    cli.execute(work)
                    result = cli.result(owner)
                    self.assertEqual(result.status, status)
                    self.assertIs(result.error, original)
                    self.assertEqual(replies[0][0], 502)
                    self.assertNotIn(b'synthetic-private-cause', replies[0][1])
                    unhandled.assert_not_called()
                self.assertIs(owner.state, OwnerState.RELEASED)
                self.assertFalse((Path(directory) / 'test-environment.lock').exists())

    def test_http_converted_stop_failure_is_retained_after_successful_final_retry(self):
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled), tempfile.TemporaryDirectory() as directory, CliSignalScope() as cli:
                owner = TestEnvironmentOwner(directory, cancellation=cli.cancellation)
                transport = GuestTransport({'ssh_user': 'fixture', 'access_key': 'fixture', 'ssh_port': 2222}, directory)
                proxy = AppiumProxy('http://127.0.0.1:1', transport,
                                   {'launch': {}, 'cleanup_roots': []}, Path(directory))
                proxy.launch = Mock()
                child = Mock()
                child.poll.return_value = None
                child.stdin = child.stdout = child.stderr = None
                child.returncode = 0
                requested = threading.Event()
                original_stop = OSError('synthetic-private-stop /private/path')
                stops = []
                def stop():
                    stops.append(threading.get_ident())
                    if len(stops) == 1:
                        raise original_stop
                    signal.raise_signal(signal.SIGINT)
                    signal.raise_signal(signal.SIGINT)
                child.terminate.side_effect = stop
                if cancelled:
                    def communicate(**options):
                        cli.cancellation.request(signal.SIGTERM)
                        requested.set()
                        raise subprocess.TimeoutExpired('fixture', .1)
                    child.communicate.side_effect = communicate
                else:
                    child.communicate.return_value = (b'OK', b'')
                proxy.launch.prepare.side_effect = lambda caps: transport.run(['fixture'])
                response, client_errors = [], []
                def client():
                    connection = http.client.HTTPConnection('127.0.0.1', proxy.server.server_port, timeout=5)
                    try:
                        connection.request('POST', '/session', b'{"desiredCapabilities":{}}')
                        reply = connection.getresponse()
                        response.append((reply.status, reply.read()))
                    except BaseException as error:
                        client_errors.append(error)
                    finally:
                        connection.close()
                thread = threading.Thread(target=client)
                def work():
                    with owner:
                        owner.callback(transport.close)
                        owner.callback(proxy.close)
                        proxy.start()
                        thread.start()
                        if cancelled:
                            self.assertTrue(requested.wait(5))
                            owner.checkpoint()
                        else:
                            thread.join(timeout=5)
                            self.assertFalse(thread.is_alive())
                        return 23
                output = io.StringIO()
                writes = []
                write = owner_module.write_record
                def publish(path, record):
                    writes.append(threading.get_ident())
                    return write(path, record)
                try:
                    with patch('test_guest_transport.subprocess.Popen', return_value=child) as launch, \
                            patch.object(owner_module, 'write_record', side_effect=publish), redirect_stdout(io.StringIO()):
                        cli.execute(work)
                    result = cli.result(owner)
                    report_cleanup(result.cleanup, output)
                    thread.join(timeout=5)
                    self.assertFalse(thread.is_alive())
                    self.assertEqual(client_errors, [])
                    self.assertEqual(response[0][0], 502)
                    self.assertNotIn(b'synthetic-private-stop', response[0][1])
                    self.assertEqual(result.status, 143 if cancelled else 1)
                    if cancelled:
                        self.assertIs(result.error, cli.cancellation.accepted)
                    self.assertTrue(result.cleanup.lease_retained)
                    self.assertIn(('io', 1), result.cleanup.categories)
                    self.assertIn('Guest test lease retained', output.getvalue())
                    self.assertNotIn('synthetic-private-stop', output.getvalue())
                    self.assertNotIn('/private/path', output.getvalue())
                    self.assertNotIn('Traceback', output.getvalue())
                    record = json.loads((Path(directory) / 'test-environment.lock/owner.json').read_text())
                    self.assertEqual(record['phase'], 'cleanup-uncertain')
                    self.assertEqual(child.terminate.call_count, 2)
                    launch.assert_called_once()
                    self.assertEqual(stops[-1], threading.main_thread().ident)
                    self.assertTrue(writes)
                    self.assertEqual(set(writes), {threading.main_thread().ident})
                finally:
                    if thread.ident is not None:
                        thread.join(timeout=5)
                    if proxy.thread.ident is None:
                        proxy.server.server_close()


if __name__ == '__main__':
    unittest.main()
