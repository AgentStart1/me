"""Resource ownership persists retention before later teardown can mask a failure."""
from contextlib import ExitStack, redirect_stdout
import io
import inspect
import json
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_environment as environment
from test_appium_proxy import CleanupUncertain
from test_environment_owner import EnvironmentCleanupError, TestEnvironmentOwner, OwnerState
from resource_ownership import Cancelled
from test_guest_transport import GuestTransport, TransportCleanupError


class EnvironmentOwnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.lock = self.home / 'test-environment.lock'

    def record(self):
        return json.loads((self.lock / 'owner.json').read_text())

    def test_drained_publication_runs_after_resources_and_workers_before_release(self):
        events = []
        owner = TestEnvironmentOwner(self.home)
        def publish(error):
            self.assertIsNone(error)
            self.assertEqual(owner.state, OwnerState.DRAINED)
            self.assertEqual(events, ['resource', 'workers'])
            self.assertEqual(self.record()['token'], owner.token)
            with self.assertRaises(FileExistsError):
                with TestEnvironmentOwner(self.home):
                    self.fail('Publication lost its reservation')
            with self.assertRaises(RuntimeError):
                owner.callback(lambda: None)
            events.append('published')
        with patch.object(owner, '_finish_workers', side_effect=lambda: events.append('workers')):
            with owner:
                owner.callback(lambda: events.append('resource'))
                owner.on_drained(publish)
        self.assertEqual(events, ['resource', 'workers', 'published'])
        self.assertFalse(self.lock.exists())

    def test_failed_publication_retains_the_lease(self):
        with self.assertRaisesRegex(OSError, 'publication failed'):
            with TestEnvironmentOwner(self.home) as owner:
                owner.on_drained(Mock(side_effect=OSError('publication failed')))
        self.assertIs(owner.state, OwnerState.RETAINED)
        self.assertEqual(self.record()['phase'], 'cleanup-uncertain')

    def test_publication_can_report_uncertainty_without_releasing_the_lease(self):
        with self.assertRaises(CleanupUncertain):
            with TestEnvironmentOwner(self.home) as owner:
                owner.on_drained(lambda error: owner.retain())
        self.assertIs(owner.state, OwnerState.RETAINED)

    def test_lost_lease_identity_prevents_terminal_publication(self):
        publish = Mock()
        with self.assertRaisesRegex(RuntimeError, 'refusing publication'):
            with TestEnvironmentOwner(self.home) as owner:
                owner.on_drained(publish)
                record = self.record()
                (self.lock / 'owner.json').write_text(json.dumps({**record, 'token': 'replacement'}))
        publish.assert_not_called()
        self.assertIs(owner.state, OwnerState.RETAINED)

    def test_body_failure_is_published_before_clean_lease_release(self):
        failure = ValueError('fixture failure')
        def publish(error):
            self.assertIs(error, failure)
            self.assertTrue(self.lock.exists())
        callback = Mock(side_effect=publish)
        with self.assertRaises(ValueError):
            with TestEnvironmentOwner(self.home) as owner:
                owner.on_drained(callback)
                raise failure
        callback.assert_called_once()
        self.assertFalse(self.lock.exists())

    def test_success_releases_only_after_all_owned_resources_close(self):
        order = []
        with TestEnvironmentOwner(self.home) as owner:
            def close(name):
                self.assertTrue(self.lock.exists()); order.append(name)
            owner.callback(close, 'transport'); owner.callback(close, 'proxy')
        self.assertEqual(order, ['proxy', 'transport'])
        self.assertEqual(owner.state, OwnerState.RELEASED)
        self.assertFalse(self.lock.exists())

    def test_later_cleanup_failure_cannot_erase_published_retention(self):
        order = []
        def proxy_close():
            order.append('proxy'); raise CleanupUncertain('creation unresolved')
        def transport_close():
            self.assertEqual(self.record()['phase'], 'cleanup-uncertain')
            order.append('transport'); raise OSError('transport cleanup failed')
        with self.assertRaisesRegex(OSError, 'transport cleanup'):
            with TestEnvironmentOwner(self.home) as owner:
                owner.callback(transport_close); owner.callback(proxy_close)
        self.assertEqual(order, ['proxy', 'transport'])
        self.assertEqual(owner.state, OwnerState.RETAINED)
        self.assertEqual(self.record()['phase'], 'cleanup-uncertain')
        with self.assertRaises(FileExistsError):
            with TestEnvironmentOwner(self.home): self.fail('Retained lease was stolen')

    def test_context_cleanup_failure_retains_lease(self):
        manager = Mock(); manager.__enter__ = Mock(return_value='resource')
        manager.__exit__ = Mock(side_effect=PermissionError('temporary directory in use'))
        with self.assertRaises(PermissionError):
            with TestEnvironmentOwner(self.home) as owner:
                self.assertEqual(owner.enter_context(manager), 'resource')
        self.assertEqual(self.record()['phase'], 'cleanup-uncertain')

    def test_cleanup_interruption_retains_lease_and_closes_remaining_resources(self):
        remaining = Mock()
        def interrupt(): raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            with TestEnvironmentOwner(self.home) as owner:
                owner.callback(remaining); owner.callback(interrupt)
        remaining.assert_called_once()
        self.assertEqual(self.record()['phase'], 'cleanup-uncertain')

    def test_ordinary_test_failure_releases_confirmed_clean_resources(self):
        closed = Mock()
        with self.assertRaisesRegex(ValueError, 'test failed'):
            with TestEnvironmentOwner(self.home) as owner:
                owner.callback(closed); raise ValueError('test failed')
        closed.assert_called_once(); self.assertFalse(self.lock.exists())

    def test_retention_write_failure_keeps_reservation_and_continues_cleanup(self):
        remaining = Mock()
        def fail(): raise CleanupUncertain('remote unresolved')
        owner = TestEnvironmentOwner(self.home); owner.__enter__()
        owner.callback(remaining); owner.callback(fail)
        with patch('test_environment_owner.write_record', side_effect=OSError('disk write')):
            with self.assertRaisesRegex(OSError, 'disk write'):
                owner.__exit__(None, None, None)
        remaining.assert_called_once()
        self.assertEqual(owner.state, OwnerState.RETAINED)
        self.assertTrue(self.lock.exists())

    def test_incoming_uncertainty_closes_resources_even_if_retention_write_fails(self):
        owner = TestEnvironmentOwner(self.home); owner.__enter__(); closed = Mock(); owner.callback(closed)
        error = CleanupUncertain('host shutdown unresolved')
        with patch('test_environment_owner.write_record', side_effect=OSError('disk write')):
            with self.assertRaises(OSError): owner.__exit__(type(error), error, None)
        closed.assert_called_once(); self.assertTrue(self.lock.exists())
        self.assertEqual(owner.state, OwnerState.RETAINED)

    def test_failed_initial_publication_preserves_its_own_reservation(self):
        owner = TestEnvironmentOwner(self.home)
        with patch('test_environment_owner.write_record', side_effect=OSError('disk write')):
            with self.assertRaises(OSError): owner.__enter__()
        self.assertTrue(self.lock.exists())
        self.assertEqual(owner.state, OwnerState.RETAINED)

    def test_changed_owner_is_never_deleted_or_overwritten(self):
        with self.assertRaisesRegex(RuntimeError, 'ownership changed'):
            with TestEnvironmentOwner(self.home):
                (self.lock / 'owner.json').write_text('{"token":"foreign","phase":"active"}')
        self.assertEqual(self.record(), {'token': 'foreign', 'phase': 'active'})

    def test_context_suppression_cannot_report_uncertain_cleanup_as_success(self):
        manager = Mock(); manager.__enter__ = Mock(); manager.__exit__ = Mock(return_value=True)
        def fail(): raise OSError('cleanup failed')
        with self.assertRaises(CleanupUncertain):
            with TestEnvironmentOwner(self.home) as owner:
                owner.enter_context(manager); owner.callback(fail)
        self.assertEqual(self.record()['phase'], 'cleanup-uncertain')

    def test_real_run_retains_lease_when_transport_masks_proxy_failure(self):
        guest = {'os': 'ubuntu', 'state_dir': str(self.home), 'ssh_port': 2222}
        transport = Mock(); transport.close.side_effect = OSError('transport cleanup failed')
        proxy = Mock(); proxy.close.side_effect = CleanupUncertain('creation unresolved')
        opener = Mock(); opener.open.return_value = io.BytesIO(b'{"value":{"ready":true}}')
        tree = Mock(); tree.start.return_value.wait.return_value = 0
        patches = {'guest_config': Mock(return_value=guest),
                   'entries': Mock(return_value=[{'state_dir': str(self.home)}]),
                   'state': Mock(return_value=('ready', {'pid': 123})),
                   'owns_listeners': Mock(return_value=True), 'LinuxTransport': Mock(return_value=transport),
                   'AppiumProxy': Mock(return_value=proxy), 'CommandTree': Mock(return_value=tree)}
        with patch.multiple(environment, **patches), \
                patch.object(environment.urllib.request, 'build_opener', return_value=opener), \
                redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(OSError, 'transport cleanup'):
                environment.run({'workspace': self.home, 'environment': {}, 'appium': {'guest': 'fixture'}},
                                [sys.executable, '-c', 'pass'])
        proxy.close.assert_called_once(); transport.close.assert_called_once(); tree.stop.assert_called_once()
        self.assertEqual(self.record()['phase'], 'cleanup-uncertain')

    def test_resource_acquisition_requires_an_active_owner(self):
        owner = TestEnvironmentOwner(self.home)
        for phase in ['before-enter', 'after-release']:
            with self.subTest(phase=phase):
                resource = Mock(); resource.__enter__ = Mock()
                with self.assertRaises(RuntimeError): owner.enter_context(resource)
                resource.__enter__.assert_not_called()
                with self.assertRaises(RuntimeError): owner.callback(Mock())
                with self.assertRaises(RuntimeError): owner.acquire_lease(self.home)
                with self.assertRaises(RuntimeError): owner.retain()
                if phase == 'before-enter':
                    with owner: pass
        self.assertFalse(self.lock.exists())

    def test_optional_guest_lease_cannot_be_replaced_with_another_reservation(self):
        other = self.home / 'other'
        other.mkdir()
        with TestEnvironmentOwner() as owner:
            owner.acquire_lease(self.home)
            record = self.record()
            with self.assertRaises(RuntimeError):
                owner.acquire_lease(other)
            self.assertEqual(self.record(), record)
            self.assertFalse((other / 'test-environment.lock').exists())
        self.assertFalse(self.lock.exists())

    def test_incoming_cancellation_survives_all_cleanup_failures(self):
        cancellation = Cancelled(2)
        failures = [OSError('proxy'), PermissionError('transport')]
        callbacks = [Mock(side_effect=failure) for failure in failures]
        with self.assertRaises(Cancelled) as raised:
            with TestEnvironmentOwner(self.home) as owner:
                for callback in reversed(callbacks):
                    owner.callback(callback)
                raise cancellation
        self.assertIs(raised.exception, cancellation)
        self.assertEqual(raised.exception.status, 130)
        self.assertEqual(raised.exception.__cause__.failures, tuple(failures))
        for callback in callbacks:
            callback.assert_called_once()
        self.assertEqual(self.record()['phase'], 'cleanup-uncertain')

    def test_cleanup_cancellation_survives_later_cleanup_failure(self):
        cancellation = KeyboardInterrupt()
        failure = OSError('later cleanup')
        with self.assertRaises(KeyboardInterrupt) as raised:
            with TestEnvironmentOwner(self.home) as owner:
                owner.callback(Mock(side_effect=failure))
                owner.callback(Mock(side_effect=cancellation))
        self.assertIs(raised.exception, cancellation)
        self.assertEqual(raised.exception.__cause__.failures, (failure,))
        self.assertEqual(self.record()['phase'], 'cleanup-uncertain')

    def test_clean_cancellation_releases_lease_and_preserves_identity(self):
        for cancellation in (Cancelled(2), KeyboardInterrupt(), SystemExit(7)):
            with self.subTest(kind=type(cancellation)):
                with self.assertRaises(type(cancellation)) as raised:
                    with TestEnvironmentOwner(self.home):
                        raise cancellation
                self.assertIs(raised.exception, cancellation)
                self.assertFalse(self.lock.exists())

    def test_context_suppression_cannot_swallow_cancellation(self):
        manager = Mock()
        manager.__enter__ = Mock()
        manager.__exit__ = Mock(return_value=True)
        cancellation = Cancelled(2)
        with self.assertRaises(Cancelled) as raised:
            with TestEnvironmentOwner(self.home) as owner:
                owner.enter_context(manager)
                raise cancellation
        self.assertIs(raised.exception, cancellation)
        self.assertFalse(self.lock.exists())

    def test_retention_publication_failure_is_attached_to_cancellation(self):
        cancellation = Cancelled(2)
        failure = OSError('stop failed')
        publication = OSError('publication failed')
        remaining = Mock()
        owner = TestEnvironmentOwner(self.home)
        owner.__enter__()
        owner.callback(remaining)
        owner.callback(Mock(side_effect=failure))
        with self.assertRaises(Cancelled) as raised:
            with patch('test_environment_owner.write_record', side_effect=publication):
                owner.__exit__(type(cancellation), cancellation, None)
        self.assertIs(raised.exception, cancellation)
        self.assertIn(failure, raised.exception.__cause__.failures)
        self.assertIn(publication, raised.exception.__cause__.failures)
        remaining.assert_called_once()
        self.assertTrue(self.lock.exists())

    def test_transport_child_aggregate_survives_environment_cancellation(self):
        transport = object.__new__(GuestTransport)
        transport.children = [object(), object()]
        failure = OSError('child stop failed')
        transport.stop = Mock(side_effect=[failure, None])
        cancellation = Cancelled(2)
        with self.assertRaises(Cancelled) as raised:
            with TestEnvironmentOwner(self.home) as owner:
                owner.callback(transport.close)
                raise cancellation
        aggregate = raised.exception.__cause__
        self.assertIsInstance(aggregate, EnvironmentCleanupError)
        self.assertIsInstance(aggregate.failures[0], TransportCleanupError)
        self.assertEqual(aggregate.failures[0].failures, (failure,))
        self.assertEqual(transport.stop.call_count, 2)
        self.assertEqual(self.record()['phase'], 'cleanup-uncertain')

    def test_transport_cleanup_cancellation_keeps_child_failures_attached(self):
        transport = object.__new__(GuestTransport)
        transport.children = [object(), object()]
        cancellation, failure = Cancelled(2), OSError('child stop failed')
        transport.stop = Mock(side_effect=[cancellation, failure])
        with self.assertRaises(Cancelled) as raised:
            with TestEnvironmentOwner(self.home) as owner:
                owner.callback(transport.close)
        child_aggregate = raised.exception.__cause__.failures[0]
        self.assertIsInstance(child_aggregate, TransportCleanupError)
        self.assertEqual(child_aggregate.failures, (cancellation, failure))
        self.assertIs(raised.exception, cancellation)
        self.assertEqual(self.record()['phase'], 'cleanup-uncertain')

    def test_signal_during_cleanup_preserves_first_cancellation_and_drains_callbacks(self):
        failures = []
        def cancel(number, frame):
            cancellation = Cancelled(number)
            failures.append(cancellation)
            raise cancellation
        def interrupt():
            signal.raise_signal(signal.SIGINT)
            raise OSError('unconfirmed cleanup')
        remaining = Mock()
        previous = signal.signal(signal.SIGINT, cancel)
        try:
            with self.assertRaises(Cancelled) as raised:
                with TestEnvironmentOwner(self.home) as owner:
                    owner.callback(remaining)
                    owner.callback(interrupt)
                    owner.callback(interrupt)
        finally:
            signal.signal(signal.SIGINT, previous)
        self.assertIs(raised.exception, failures[0])
        # Repeated handled signals coalesce until the whole drain is committed.
        self.assertEqual(len(failures), 1)
        self.assertEqual(len(raised.exception.__cause__.failures), 2)
        self.assertTrue(all(isinstance(error, OSError) for error in raised.exception.__cause__.failures))
        remaining.assert_called_once()
        self.assertEqual(self.record()['phase'], 'cleanup-uncertain')

    def test_release_failure_does_not_replace_incoming_cancellation(self):
        cancellation, failure = Cancelled(2), OSError('release read failed')
        owner = TestEnvironmentOwner(self.home)
        owner.__enter__()
        with patch.object(Path, 'read_text', side_effect=failure):
            with self.assertRaises(Cancelled) as raised:
                owner.__exit__(type(cancellation), cancellation, None)
        self.assertIs(raised.exception, cancellation)
        self.assertEqual(raised.exception.__cause__.failures, (failure,))
        self.assertTrue(self.lock.exists())
        self.assertEqual(owner.state, OwnerState.RETAINED)

    def test_repeated_signals_between_failed_cleanup_and_retention_cannot_unlock(self):
        source, start = inspect.getsourcelines(TestEnvironmentOwner.cleanup)
        boundary = start + next(index for index, line in enumerate(source)
                                if line.strip() == 'self.retain()')
        delivered = []
        def cancel(number, frame):
            error = Cancelled(number)
            delivered.append(error)
            raise error
        def inject(frame, event, argument):
            if event == 'line' and frame.f_code is TestEnvironmentOwner.cleanup.__code__ and frame.f_lineno == boundary:
                sys.settrace(None)
                signal.raise_signal(signal.SIGINT)
                signal.raise_signal(signal.SIGINT)
            return inject
        failure = OSError('unconfirmed child stop')
        remaining = Mock()
        previous = signal.signal(signal.SIGINT, cancel)
        previous_trace = sys.gettrace()
        try:
            with self.assertRaises(Cancelled) as raised:
                with TestEnvironmentOwner(self.home) as owner:
                    owner.callback(remaining)
                    owner.callback(Mock(side_effect=failure))
                    sys.settrace(inject)
        finally:
            sys.settrace(previous_trace)
            signal.signal(signal.SIGINT, previous)
        self.assertIs(raised.exception, delivered[0])
        self.assertEqual(owner.state, OwnerState.RETAINED)
        self.assertEqual(self.record()['phase'], 'cleanup-uncertain')
        self.assertIn(failure, raised.exception.__cause__.failures)
        remaining.assert_called_once()

    def test_repeated_signals_during_publication_preserve_both_failures(self):
        stop_failure, publication_failure = OSError('stop'), OSError('publication')
        cancellation = Cancelled(2)
        delivered = Mock(side_effect=cancellation)
        def publish(*args, **kwargs):
            signal.raise_signal(signal.SIGINT)
            signal.raise_signal(signal.SIGINT)
            raise publication_failure
        owner = TestEnvironmentOwner(self.home)
        owner.__enter__()
        remaining = Mock()
        owner.callback(remaining)
        owner.callback(Mock(side_effect=stop_failure))
        previous = signal.signal(signal.SIGINT, delivered)
        try:
            with patch('test_environment_owner.write_record', side_effect=publish):
                with self.assertRaises(Cancelled) as raised:
                    owner.__exit__(None, None, None)
        finally:
            signal.signal(signal.SIGINT, previous)
        self.assertIs(raised.exception, cancellation)
        self.assertEqual(raised.exception.__cause__.failures, (stop_failure, publication_failure))
        self.assertEqual(owner.state, OwnerState.RETAINED)
        self.assertTrue(self.lock.exists())
        remaining.assert_called_once()
        delivered.assert_called_once()

    def test_direct_cleanup_protects_failure_recording_before_retention(self):
        failure, cancellation = OSError('stop failed'), Cancelled(2)
        remaining = Mock()
        previous = signal.signal(signal.SIGINT, Mock(side_effect=cancellation))
        try:
            with self.assertRaises(Cancelled) as raised:
                with TestEnvironmentOwner(self.home) as owner:
                    owner.callback(remaining)
                    observe = owner._observe
                    def interrupted_record(error, cleanup=False):
                        if error is failure:
                            signal.raise_signal(signal.SIGINT)
                            signal.raise_signal(signal.SIGINT)
                        observe(error, cleanup)
                    with patch.object(owner, '_observe', side_effect=interrupted_record):
                        owner.cleanup(Mock(side_effect=failure))
        finally:
            signal.signal(signal.SIGINT, previous)
        self.assertIs(raised.exception, cancellation)
        self.assertIn(failure, raised.exception.__cause__.failures)
        self.assertEqual(self.record()['phase'], 'cleanup-uncertain')
        remaining.assert_called_once()

    def test_repeated_signals_during_confirmed_cleanup_allow_clean_release(self):
        cancellation = Cancelled(2)
        order = []
        delivered = Mock(side_effect=cancellation)
        def stop():
            signal.raise_signal(signal.SIGINT)
            signal.raise_signal(signal.SIGINT)
            order.append('stop-confirmed')
        def remaining():
            self.assertEqual(self.record()['phase'], 'active')
            self.assertEqual(delivered.call_count, 0)
            order.append('remaining-confirmed')
        previous = signal.signal(signal.SIGINT, delivered)
        try:
            with self.assertRaises(Cancelled) as raised:
                with TestEnvironmentOwner(self.home) as owner:
                    owner.callback(remaining)
                    owner.callback(stop)
        finally:
            signal.signal(signal.SIGINT, previous)
        self.assertIs(raised.exception, cancellation)
        self.assertEqual(order, ['stop-confirmed', 'remaining-confirmed'])
        self.assertEqual(owner.state, OwnerState.RELEASED)
        self.assertFalse(self.lock.exists())
        self.assertIsNone(raised.exception.__cause__)

    def test_incoming_cancellation_wins_over_repeated_deferred_signals(self):
        original, later = Cancelled(15), Cancelled(2)
        failure = OSError('cleanup')
        def stop():
            signal.raise_signal(signal.SIGINT)
            signal.raise_signal(signal.SIGINT)
            raise failure
        previous = signal.signal(signal.SIGINT, Mock(side_effect=later))
        try:
            with self.assertRaises(Cancelled) as raised:
                with TestEnvironmentOwner(self.home) as owner:
                    owner.callback(stop)
                    raise original
        finally:
            signal.signal(signal.SIGINT, previous)
        self.assertIs(raised.exception, original)
        self.assertIn(failure, raised.exception.__cause__.failures)
        self.assertEqual(self.record()['phase'], 'cleanup-uncertain')

    def test_unexpected_drain_failure_never_commits_release(self):
        failure = OSError('drain did not complete')
        owner = TestEnvironmentOwner(self.home)
        owner.__enter__()
        with self.assertRaises(OSError) as raised:
            with patch.object(owner._resources, '__exit__', side_effect=failure):
                owner.__exit__(None, None, None)
        self.assertIs(raised.exception, failure)
        self.assertEqual(owner.state, OwnerState.RETAINED)
        self.assertEqual(self.record()['phase'], 'cleanup-uncertain')

    def test_real_run_preserves_wait_cancellation_before_process_tree_cleanup(self):
        guest = {'os': 'ubuntu', 'state_dir': str(self.home), 'ssh_port': 2222}
        transport, proxy, tree = Mock(), Mock(), Mock()
        cancellation = Cancelled(2)
        tree.start.return_value.wait.side_effect = cancellation
        failures = [OSError('tree'), OSError('proxy'), OSError('transport')]
        tree.stop.side_effect, proxy.close.side_effect, transport.close.side_effect = failures
        opener = Mock()
        opener.open.return_value = io.BytesIO(b'{"value":{"ready":true}}')
        patches = {'guest_config': Mock(return_value=guest),
                   'entries': Mock(return_value=[{'state_dir': str(self.home)}]),
                   'state': Mock(return_value=('ready', {'pid': 123})),
                   'owns_listeners': Mock(return_value=True), 'LinuxTransport': Mock(return_value=transport),
                   'AppiumProxy': Mock(return_value=proxy), 'CommandTree': Mock(return_value=tree)}
        with patch.multiple(environment, **patches), \
                patch.object(environment.urllib.request, 'build_opener', return_value=opener), \
                redirect_stdout(io.StringIO()):
            with self.assertRaises(Cancelled) as raised:
                environment.run({'workspace': self.home, 'environment': {}, 'appium': {'guest': 'fixture'}},
                                [sys.executable, '-c', 'pass'])
        self.assertIs(raised.exception, cancellation)
        self.assertEqual(raised.exception.__cause__.failures, tuple(failures))
        tree.stop.assert_called_once()
        proxy.close.assert_called_once()
        transport.close.assert_called_once()
        self.assertEqual(self.record()['phase'], 'cleanup-uncertain')


if __name__ == '__main__': unittest.main()
