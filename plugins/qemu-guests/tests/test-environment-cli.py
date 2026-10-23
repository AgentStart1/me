"""All execution modes share cleanup ownership and privacy-safe CLI outcomes."""
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
import io
import inspect
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_environment as environment
from resource_ownership import Cancelled, signals
from test_cleanup_diagnostics import failure_categories
from test_environment_owner import EnvironmentCleanupError, TestEnvironmentOwner, OwnerState
from test_guest_transport import TransportCleanupError
from test_cli_lifecycle import CliSignalScope, CliPhase
from test_cancellation import CancellationRequest, CancellationPhase, cancellation_context, current_cancellation
import test_cli_lifecycle as lifecycle


class EnvironmentCliTests(unittest.TestCase):
    @contextmanager
    def scenario(self, mode):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as resources:
            home = Path(directory)
            state = home / 'guest-state'
            state.mkdir()
            config = {'workspace': home, 'environment': {}}
            if mode == 'docker':
                config['docker'] = home / 'backend.profile'
            elif mode == 'guest':
                config['appium'] = {'guest': home / 'guest.json'}
            guest = {'os': 'ubuntu', 'state_dir': str(state), 'ssh_port': 2222}
            tree, transport, proxy = Mock(), Mock(), Mock()
            tree.start.return_value.wait.return_value = 23
            opener = Mock()
            opener.open.return_value = io.BytesIO(b'{"value":{"ready":true}}')
            patches = {'load': Mock(return_value=config), 'guest_config': Mock(return_value=guest),
                       'entries': Mock(return_value=[{'state_dir': str(state)}]),
                       'state': Mock(return_value=('ready', {'pid': 123})),
                       'owns_listeners': Mock(return_value=True), 'LinuxTransport': Mock(return_value=transport),
                       'AppiumProxy': Mock(return_value=proxy), 'CommandTree': Mock(return_value=tree)}
            resources.enter_context(patch.multiple(environment, **patches))
            resources.enter_context(patch.object(environment.urllib.request, 'build_opener', return_value=opener))
            resources.enter_context(patch.object(environment.shutil, 'which',
                                                 side_effect=lambda value: 'bash' if value == 'bash' else value))
            output, errors = io.StringIO(), io.StringIO()
            resources.enter_context(redirect_stdout(output))
            resources.enter_context(redirect_stderr(errors))
            yield config, tree, state, errors, patches

    def cli(self):
        return environment.main(['--config', 'fixture.json', '--', sys.executable, '-c', 'pass'])

    @contextmanager
    def interrupt_handoff_at(self, statement, method=None, scope=None):
        method = CliSignalScope.execute if method is None else method
        source, start = inspect.getsourcelines(method)
        target = start + next(index for index, line in enumerate(source) if line.strip() == statement)
        injected = []
        def inject(frame, event, argument):
            if event == 'line' and frame.f_code is method.__code__ and frame.f_lineno == target:
                sys.settrace(None)
                current_scope = scope if scope is not None else frame.f_locals['self']
                injected.append(current_scope.outcome)
                try:
                    signal.raise_signal(signal.SIGINT)
                finally:
                    signal.raise_signal(signal.SIGINT)
            return inject
        previous_trace = sys.gettrace()
        sys.settrace(inject)
        try:
            yield injected
        finally:
            sys.settrace(previous_trace)

    def test_all_modes_preserve_cancellation_despite_process_tree_failure(self):
        for mode in ('local', 'docker', 'guest'):
            with self.subTest(mode=mode), self.scenario(mode) as (_, tree, state, errors, _):
                tree.start.return_value.wait.side_effect = Cancelled(2)
                tree.stop.side_effect = OSError('secret-token /private/path\ninjected text')
                self.assertEqual(self.cli(), 130)
                tree.stop.assert_called_once()
                self.assertIn('io=1', errors.getvalue())
                self.assertNotIn('secret-token', errors.getvalue())
                self.assertNotIn('/private/path', errors.getvalue())
                if mode == 'guest':
                    self.assertIn('Guest test lease retained', errors.getvalue())
                    self.assertEqual(json.loads((state / 'test-environment.lock/owner.json').read_text())['phase'],
                                     'cleanup-uncertain')
                else:
                    self.assertIn('No guest test lease was acquired', errors.getvalue())
                    self.assertFalse((state / 'test-environment.lock').exists())

    def test_all_modes_release_clean_cancellation_without_cleanup_warning(self):
        for mode in ('local', 'docker', 'guest'):
            with self.subTest(mode=mode), self.scenario(mode) as (_, tree, state, errors, _):
                tree.start.return_value.wait.side_effect = Cancelled(2)
                self.assertEqual(self.cli(), 130)
                self.assertEqual(errors.getvalue(), '')
                self.assertFalse((state / 'test-environment.lock').exists())

    def test_all_modes_report_ordinary_cleanup_failures_without_raw_tracebacks(self):
        for mode in ('local', 'docker', 'guest'):
            with self.subTest(mode=mode), self.scenario(mode) as (_, tree, _, errors, _):
                private_error = type('SecretClassName', (RuntimeError,), {})
                tree.stop.side_effect = private_error('secret arguments')
                self.assertEqual(self.cli(), 1)
                self.assertIn('operation=1', errors.getvalue())
                self.assertNotIn('secret arguments', errors.getvalue())
                self.assertNotIn('SecretClassName', errors.getvalue())
                self.assertNotIn('Traceback', errors.getvalue())

    def test_all_modes_preserve_host_exit_code_after_confirmed_cleanup(self):
        for mode in ('local', 'docker', 'guest'):
            with self.subTest(mode=mode), self.scenario(mode) as (_, tree, state, errors, _):
                self.assertEqual(self.cli(), 23)
                tree.stop.assert_called_once()
                self.assertEqual(errors.getvalue(), '')
                self.assertFalse((state / 'test-environment.lock').exists())

    def test_all_modes_own_partial_startup_before_it_can_be_cancelled(self):
        for mode in ('local', 'docker', 'guest'):
            with self.subTest(mode=mode), self.scenario(mode) as (_, tree, _, errors, _):
                tree.start.side_effect = Cancelled(15)
                tree.stop.side_effect = TimeoutError('private executable')
                self.assertEqual(self.cli(), 143)
                tree.stop.assert_called_once()
                self.assertIn('timeout=1', errors.getvalue())

    def test_all_modes_ignore_late_signals_during_failed_cleanup(self):
        for mode in ('local', 'docker', 'guest'):
            with self.subTest(mode=mode), self.scenario(mode) as (_, tree, _, errors, _):
                def stop():
                    signal.raise_signal(signal.SIGINT)
                    signal.raise_signal(signal.SIGINT)
                    raise OSError('secret process')
                tree.stop.side_effect = stop
                self.assertEqual(self.cli(), 1)
                self.assertIn('io=1', errors.getvalue())

    def test_local_and_docker_use_same_owner_without_acquiring_a_guest_lease(self):
        for mode in ('local', 'docker'):
            with self.subTest(mode=mode), self.scenario(mode) as (config, tree, _, _, patches):
                owner, cancellation = TestEnvironmentOwner(), Cancelled(2)
                failure = OSError('stop failed')
                tree.start.return_value.wait.side_effect = cancellation
                tree.stop.side_effect = failure
                with self.assertRaises(Cancelled) as raised:
                    environment.run(config, [sys.executable], owner=owner)
                self.assertIs(raised.exception, cancellation)
                self.assertEqual(raised.exception.__cause__.failures, (failure,))
                self.assertEqual(owner.state, OwnerState.RETAINED)
                self.assertIsNone(owner.path)
                self.assertFalse(owner.lease_retained)
                patches['guest_config'].assert_not_called()

    def test_cli_summarizes_nested_transport_failures_without_exception_text(self):
        with self.scenario('guest') as (_, tree, _, errors, _):
            tree.start.return_value.wait.side_effect = Cancelled(2)
            environment.LinuxTransport.return_value.close.side_effect = TransportCleanupError([
                PermissionError('private identity'), subprocess.TimeoutExpired(['secret-command'], 5)])
            self.assertEqual(self.cli(), 130)
            self.assertIn('permission=1, timeout=1', errors.getvalue())
            self.assertNotIn('private identity', errors.getvalue())
            self.assertNotIn('secret-command', errors.getvalue())

    def test_cli_diagnostics_do_not_replace_cancellation_when_stderr_is_closed(self):
        closed = io.StringIO()
        closed.close()
        broken = Mock()
        broken.write.side_effect = BrokenPipeError()
        for stream in (closed, broken):
            with self.subTest(stream=type(stream)), self.scenario('local') as (_, tree, _, _, _):
                tree.start.return_value.wait.side_effect = Cancelled(2)
                tree.stop.side_effect = OSError('stop failed')
                with redirect_stderr(stream):
                    self.assertEqual(self.cli(), 130)

    def test_cli_preserves_system_exit_code_without_printing_cleanup_exception_text(self):
        with self.scenario('local') as (_, tree, _, errors, _):
            tree.start.return_value.wait.side_effect = SystemExit(7)
            tree.stop.side_effect = OSError('secret')
            self.assertEqual(self.cli(), 7)
            self.assertIn('io=1', errors.getvalue())
            self.assertNotIn('secret', errors.getvalue())

    def test_cli_restores_callers_signal_handlers(self):
        with self.scenario('local') as (_, tree, _, _, _):
            before = {number: signal.getsignal(number) for number in signals()}
            tree.start.return_value.wait.side_effect = Cancelled(2)
            self.assertEqual(self.cli(), 130)
            self.assertEqual({number: signal.getsignal(number) for number in before}, before)

    def test_existing_foreign_guest_lease_is_never_claimed_or_removed(self):
        with self.scenario('guest') as (config, tree, state, _, _):
            lock = state / 'test-environment.lock'
            lock.mkdir()
            record = lock / 'owner.json'
            record.write_text('{"token":"foreign"}')
            owner = TestEnvironmentOwner()
            with self.assertRaises(FileExistsError):
                environment.run(config, [sys.executable], owner=owner)
            self.assertIsNone(owner.path)
            self.assertFalse(owner.lease_retained)
            self.assertEqual(record.read_text(), '{"token":"foreign"}')
            tree.start.assert_not_called()

    def test_category_summary_handles_shared_and_cyclic_aggregates(self):
        failure = OSError('secret')
        aggregate = EnvironmentCleanupError([failure, failure])
        aggregate.failures += (aggregate,)
        self.assertEqual(failure_categories([aggregate, failure]), {'io': 1})

    def test_cli_reports_retained_reservation_when_lease_publication_is_cancelled(self):
        with self.scenario('guest') as (_, tree, state, errors, _):
            def publish(*args, **kwargs):
                signal.raise_signal(signal.SIGINT)
                raise OSError('secret owner metadata')
            with patch('test_environment_owner.write_record', side_effect=publish):
                self.assertEqual(self.cli(), 130)
            self.assertTrue((state / 'test-environment.lock').exists())
            self.assertIn('Guest test lease retained', errors.getvalue())
            self.assertIn('io=1', errors.getvalue())
            self.assertNotIn('secret owner metadata', errors.getvalue())
            tree.start.assert_not_called()

    def test_repeated_signals_during_summary_preserve_original_cancellation_in_all_modes(self):
        class InterruptedOutput(io.StringIO):
            def write(self, text):
                signal.raise_signal(signal.SIGINT)
                signal.raise_signal(signal.SIGINT)
                return super().write(text)
        for mode in ('local', 'docker', 'guest'):
            with self.subTest(mode=mode), self.scenario(mode) as (_, tree, state, _, _):
                tree.start.return_value.wait.side_effect = Cancelled(15)
                tree.stop.side_effect = OSError('PRIVATE_CLEANUP_TEXT')
                output = InterruptedOutput()
                with redirect_stderr(output):
                    self.assertEqual(self.cli(), 143)
                self.assertIn('io=1', output.getvalue())
                self.assertNotIn('PRIVATE_CLEANUP_TEXT', output.getvalue())
                if mode == 'guest':
                    self.assertIn('Guest test lease retained', output.getvalue())
                    self.assertEqual(json.loads((state / 'test-environment.lock/owner.json').read_text())['phase'],
                                     'cleanup-uncertain')
                else:
                    self.assertIn('No guest test lease was acquired', output.getvalue())

    def test_repeated_signals_during_summary_cannot_expose_ordinary_cleanup_failure(self):
        class InterruptedOutput(io.StringIO):
            def write(self, text):
                signal.raise_signal(signal.SIGINT)
                signal.raise_signal(signal.SIGINT)
                return super().write(text)
        for mode in ('local', 'docker', 'guest'):
            with self.subTest(mode=mode), self.scenario(mode) as (_, tree, _, _, _):
                tree.stop.side_effect = OSError('PRIVATE_CLEANUP_TEXT')
                output = InterruptedOutput()
                with redirect_stderr(output):
                    self.assertEqual(self.cli(), 1)
                self.assertIn('io=1', output.getvalue())
                self.assertNotIn('PRIVATE_CLEANUP_TEXT', output.getvalue())
                self.assertNotIn('Traceback', output.getvalue())

    def test_signals_during_exit_decision_cannot_change_original_status(self):
        for mode in ('local', 'docker', 'guest'):
            with self.subTest(mode=mode), self.scenario(mode) as (_, tree, _, errors, _):
                tree.start.return_value.wait.side_effect = Cancelled(15)
                tree.stop.side_effect = OSError('PRIVATE_CLEANUP_TEXT')
                decide = lifecycle.exit_status
                def interrupted_decision(error, owner):
                    signal.raise_signal(signal.SIGINT)
                    signal.raise_signal(signal.SIGINT)
                    return decide(error, owner)
                with patch.object(lifecycle, 'exit_status', side_effect=interrupted_decision):
                    self.assertEqual(self.cli(), 143)
                self.assertIn('io=1', errors.getvalue())
                self.assertNotIn('PRIVATE_CLEANUP_TEXT', errors.getvalue())

    def test_signals_during_restoration_preserve_all_committed_exit_outcomes(self):
        for mode in ('local', 'docker', 'guest'):
            for outcome, expected in (('success', 23), ('cancel', 143), ('cleanup-error', 1)):
                with self.subTest(mode=mode, outcome=outcome), self.scenario(mode) as (_, tree, state, errors, _):
                    if outcome == 'cancel':
                        tree.start.return_value.wait.side_effect = Cancelled(15)
                    if outcome != 'success':
                        tree.stop.side_effect = OSError('PRIVATE_CLEANUP_TEXT')
                    before = {number: signal.getsignal(number) for number in signals()}
                    install = signal.signal
                    scope = CliSignalScope()
                    injected = []
                    def interrupted_restore(number, handler):
                        result = install(number, handler)
                        if scope.phase is CliPhase.FINALIZING and handler == before[number]:
                            injected.append(number)
                            signal.raise_signal(signal.SIGINT)
                            signal.raise_signal(signal.SIGINT)
                        return result
                    with patch.object(environment, 'CliSignalScope', return_value=scope), \
                            patch.object(signal, 'signal', side_effect=interrupted_restore):
                        self.assertEqual(self.cli(), expected)
                    self.assertTrue(injected)
                    self.assertEqual(scope.phase, CliPhase.CLOSED)
                    self.assertEqual({number: signal.getsignal(number) for number in before}, before)
                    self.assertNotIn('PRIVATE_CLEANUP_TEXT', errors.getvalue())
                    self.assertNotIn('Traceback', errors.getvalue())
                    self.assertEqual((state / 'test-environment.lock').exists(),
                                     mode == 'guest' and outcome != 'success')

    def test_interrupted_restoration_before_handler_commit_is_completed(self):
        with self.scenario('local') as (_, tree, _, errors, _):
            tree.start.return_value.wait.side_effect = Cancelled(15)
            tree.stop.side_effect = OSError('PRIVATE_CLEANUP_TEXT')
            before = {number: signal.getsignal(number) for number in signals()}
            install = signal.signal
            scope = CliSignalScope()
            injected = []
            def interrupted_restore(number, handler):
                if scope.phase is CliPhase.FINALIZING and handler is before[number] and not injected:
                    injected.append(number)
                    raise KeyboardInterrupt()
                return install(number, handler)
            with patch.object(environment, 'CliSignalScope', return_value=scope), \
                    patch.object(signal, 'signal', side_effect=interrupted_restore):
                self.assertEqual(self.cli(), 143)
            self.assertTrue(injected)
            self.assertEqual({number: signal.getsignal(number) for number in before}, before)
            self.assertNotIn('PRIVATE_CLEANUP_TEXT', errors.getvalue())

    def test_partial_signal_installation_restores_every_published_handler(self):
        before = {number: signal.getsignal(number) for number in signals()}
        install = signal.signal
        scope = CliSignalScope()
        failure = OSError('synthetic installation failure')
        def fail_after_install(number, handler):
            result = install(number, handler)
            if scope.phase is CliPhase.RUNNING:
                raise failure
            return result
        with patch.object(signal, 'signal', side_effect=fail_after_install):
            with self.assertRaises(OSError) as raised:
                with scope:
                    self.fail('Partial installation must not run user work')
        self.assertIs(raised.exception, failure)
        self.assertEqual(scope.phase, CliPhase.CLOSED)
        self.assertEqual({number: signal.getsignal(number) for number in before}, before)

    def test_signal_handler_only_records_first_request_until_checkpoint(self):
        before = {number: signal.getsignal(number) for number in signals()}
        with CliSignalScope() as scope:
            signal.raise_signal(signal.SIGINT)
            signal.raise_signal(signal.SIGTERM)
            self.assertIsNone(scope.cancellation.accepted)
            with self.assertRaises(Cancelled) as raised:
                scope.cancellation.checkpoint()
            self.assertEqual(raised.exception.status, 130)
            outcome = scope.execute(Mock())
            self.assertIs(outcome.error, raised.exception)
            signal.raise_signal(signal.SIGTERM)
            self.assertIs(scope.outcome, outcome)
        self.assertEqual({number: signal.getsignal(number) for number in before}, before)

    def test_output_failure_combined_with_repeated_signals_keeps_cancel_status(self):
        class BrokenInterruptedOutput:
            def write(self, text):
                signal.raise_signal(signal.SIGINT)
                signal.raise_signal(signal.SIGINT)
                raise BrokenPipeError('PRIVATE_OUTPUT_TEXT')
        with self.scenario('guest') as (_, tree, state, _, _):
            tree.start.return_value.wait.side_effect = Cancelled(15)
            tree.stop.side_effect = OSError('PRIVATE_CLEANUP_TEXT')
            with redirect_stderr(BrokenInterruptedOutput()):
                self.assertEqual(self.cli(), 143)
            self.assertEqual(json.loads((state / 'test-environment.lock/owner.json').read_text())['phase'],
                             'cleanup-uncertain')

    def test_repeated_signals_at_capture_boundaries_preserve_all_results(self):
        for mode in ('local', 'docker', 'guest'):
            for kind, expected in (('success', 23), ('cancel', 143), ('cleanup-error', 1)):
                statements = ['self._outcome = outcome', 'self.phase = CliPhase.FINALIZING', 'return outcome']
                statements += ['outcome = CliSuccess(value)'] if kind == 'success' else [
                    'except BaseException as error:', 'outcome = CliFailure(error)']
                for statement in statements:
                    with self.subTest(mode=mode, kind=kind, statement=statement), self.scenario(mode) as (_, tree, state, errors, _):
                        scope = CliSignalScope()
                        original = Cancelled(15)
                        if kind == 'cancel':
                            tree.start.return_value.wait.side_effect = original
                        if kind != 'success':
                            tree.stop.side_effect = OSError('PRIVATE_CLEANUP_TEXT')
                        before = {number: signal.getsignal(number) for number in signals()}
                        with patch.object(environment, 'CliSignalScope', return_value=scope), \
                                self.interrupt_handoff_at(statement, scope=scope) as injected:
                            self.assertEqual(self.cli(), expected)
                        self.assertEqual(len(injected), 1)
                        tree.start.assert_called_once()
                        tree.start.return_value.wait.assert_called_once_with(timeout=.1)
                        tree.stop.assert_called_once()
                        self.assertEqual({number: signal.getsignal(number) for number in before}, before)
                        self.assertNotIn('PRIVATE_CLEANUP_TEXT', errors.getvalue())
                        self.assertNotIn('Traceback', errors.getvalue())
                        self.assertEqual((state / 'test-environment.lock').exists(), mode == 'guest' and kind != 'success')
                        if kind == 'cancel':
                            self.assertIs(scope.outcome.error, original)
                        if kind != 'success':
                            self.assertIn('io=1', errors.getvalue())
                            self.assertIn('Guest test lease retained' if mode == 'guest' else 'No guest test lease was acquired', errors.getvalue())

    def test_repeated_signals_at_every_final_capture_instruction_preserve_results(self):
        for kind, expected in (('success', 23), ('cancel', 143), ('cleanup-error', 1)):
            with self.subTest(kind=kind), self.scenario('guest') as (_, tree, state, errors, _):
                scope = CliSignalScope()
                completed = []
                injected = []
                if kind == 'cancel':
                    tree.start.return_value.wait.side_effect = Cancelled(15)
                def stop():
                    completed.append(True)
                    if kind != 'success':
                        raise OSError('PRIVATE_CLEANUP_TEXT')
                tree.stop.side_effect = stop
                def trace(frame, event, argument):
                    if frame.f_code is CliSignalScope.execute.__code__:
                        frame.f_trace_opcodes = True
                        if event == 'opcode' and completed:
                            injected.append(frame.f_lasti)
                            signal.raise_signal(signal.SIGINT)
                            signal.raise_signal(signal.SIGTERM)
                    return trace
                previous = sys.gettrace()
                caller = sys._getframe()
                old_opcodes = caller.f_trace_opcodes
                try:
                    with patch.object(environment, 'CliSignalScope', return_value=scope):
                        caller.f_trace_opcodes = True
                        sys.settrace(trace)
                        self.assertEqual(self.cli(), expected)
                finally:
                    sys.settrace(previous)
                    caller.f_trace_opcodes = old_opcodes
                self.assertGreater(len(injected), 5)
                tree.start.assert_called_once()
                tree.stop.assert_called_once()
                self.assertNotIn('PRIVATE_CLEANUP_TEXT', errors.getvalue())
                self.assertNotIn('Traceback', errors.getvalue())
                self.assertEqual((state / 'test-environment.lock').exists(), kind != 'success')

    def test_request_during_bounded_wait_stops_once_in_every_mode(self):
        for mode in ('local', 'docker', 'guest'):
            with self.subTest(mode=mode), self.scenario(mode) as (_, tree, state, errors, _):
                def waiting(timeout):
                    self.assertEqual(timeout, .1)
                    signal.raise_signal(signal.SIGTERM)
                    signal.raise_signal(signal.SIGINT)
                    raise subprocess.TimeoutExpired('fixture', timeout)
                tree.start.return_value.wait.side_effect = waiting
                self.assertEqual(self.cli(), 143)
                tree.start.assert_called_once()
                tree.start.return_value.wait.assert_called_once()
                tree.stop.assert_called_once()
                self.assertEqual(errors.getvalue(), '')
                self.assertFalse((state / 'test-environment.lock').exists())

    def test_normal_bounded_wait_retries_only_wait_and_keeps_command_exit_code(self):
        with self.scenario('local') as (_, tree, _, errors, _):
            tree.start.return_value.wait.side_effect = [subprocess.TimeoutExpired('fixture', .1), 23]
            self.assertEqual(self.cli(), 23)
            tree.start.assert_called_once()
            self.assertEqual(tree.start.return_value.wait.call_count, 2)
            tree.stop.assert_called_once()
            self.assertEqual(errors.getvalue(), '')

    def test_execution_and_cleanup_share_one_cancellation_owner(self):
        with self.scenario('local') as (_, tree, _, _, _):
            scope = CliSignalScope()
            construct = environment.TestEnvironmentOwner
            captured = []
            def create(*args, **kwargs):
                owner = construct(*args, **kwargs)
                captured.append(owner)
                return owner
            with patch.object(environment, 'CliSignalScope', return_value=scope), \
                    patch.object(environment, 'TestEnvironmentOwner', side_effect=create):
                self.assertEqual(self.cli(), 23)
            self.assertIs(captured[0].cancellation, scope.cancellation)
            self.assertIs(scope.cancellation.phase, CancellationPhase.FINISHED)

    def test_resource_handoffs_never_replace_cli_signal_handlers(self):
        with self.scenario('guest') as (_, tree, _, _, _):
            install = signal.signal
            with patch.object(signal, 'signal', side_effect=install) as calls:
                self.assertEqual(self.cli(), 23)
            self.assertEqual(calls.call_count, 2 * len(signals()))

    def test_repeated_signals_during_clean_cleanup_keep_host_result(self):
        with self.scenario('guest') as (_, tree, state, errors, _):
            def stop():
                signal.raise_signal(signal.SIGINT)
                signal.raise_signal(signal.SIGTERM)
            tree.stop.side_effect = stop
            self.assertEqual(self.cli(), 23)
            tree.stop.assert_called_once()
            self.assertFalse((state / 'test-environment.lock').exists())
            self.assertEqual(errors.getvalue(), '')

    def test_preflight_request_prevents_any_command_or_lease_acquisition(self):
        with self.scenario('guest') as (_, tree, state, errors, patches):
            load = patches['load']
            config = load.return_value
            def interrupted_load(_):
                signal.raise_signal(signal.SIGINT)
                signal.raise_signal(signal.SIGTERM)
                return config
            load.side_effect = interrupted_load
            self.assertEqual(self.cli(), 130)
            tree.start.assert_not_called()
            tree.stop.assert_not_called()
            self.assertFalse((state / 'test-environment.lock').exists())
            self.assertEqual(errors.getvalue(), '')

    def test_summary_runs_outside_execution_exception_handler(self):
        with self.scenario('local') as (_, tree, _, _, _):
            tree.start.return_value.wait.side_effect = Cancelled(15)
            tree.stop.side_effect = OSError('PRIVATE_CLEANUP_TEXT')
            report = environment.report_cleanup
            def verify_context(snapshot, stream):
                self.assertIsNone(sys.exc_info()[1])
                report(snapshot, stream)
            with patch.object(environment, 'report_cleanup', side_effect=verify_context) as observed:
                self.assertEqual(self.cli(), 143)
            observed.assert_called_once()

    def test_request_during_process_creation_cleans_owned_tree_without_waiting(self):
        with self.scenario('local') as (_, tree, _, errors, _):
            child = tree.start.return_value
            def start(*args, **kwargs):
                signal.raise_signal(signal.SIGTERM)
                signal.raise_signal(signal.SIGINT)
                return child
            tree.start.side_effect = start
            self.assertEqual(self.cli(), 143)
            tree.start.assert_called_once()
            child.wait.assert_not_called()
            tree.stop.assert_called_once()
            self.assertEqual(errors.getvalue(), '')

    def test_request_after_readiness_drains_transport_without_launching_proxy(self):
        with self.scenario('guest') as (_, tree, state, errors, patches):
            opener = Mock()
            def status(*args, **kwargs):
                signal.raise_signal(signal.SIGTERM)
                return io.BytesIO(b'{"value":{"ready":true}}')
            opener.open.side_effect = status
            with patch.object(environment.urllib.request, 'build_opener', return_value=opener):
                self.assertEqual(self.cli(), 143)
            patches['AppiumProxy'].assert_not_called()
            patches['LinuxTransport'].return_value.close.assert_called_once()
            tree.start.assert_not_called()
            self.assertFalse((state / 'test-environment.lock').exists())
            self.assertEqual(errors.getvalue(), '')

    def test_proxy_startup_failure_closes_registered_proxy_and_transport(self):
        with self.scenario('guest') as (_, tree, state, _, patches):
            error = RuntimeError('synthetic proxy thread startup failure')
            proxy = patches['AppiumProxy'].return_value
            proxy.start.side_effect = error
            with self.assertRaises(RuntimeError) as raised:
                self.cli()
            self.assertIs(raised.exception, error)
            proxy.close.assert_called_once()
            patches['LinuxTransport'].return_value.close.assert_called_once()
            tree.start.assert_not_called()
            self.assertFalse((state / 'test-environment.lock').exists())

    def test_committed_result_and_cleanup_snapshot_are_immutable(self):
        with CliSignalScope() as scope:
            owner = TestEnvironmentOwner(cancellation=scope.cancellation)
            def operation():
                with owner:
                    owner.callback(Mock(side_effect=OSError('PRIVATE_CLEANUP_TEXT')))
                    raise Cancelled(15)
            scope.execute(operation)
            result = scope.result(owner)
            self.assertEqual(result.status, 143)
            self.assertEqual(result.cleanup.categories, (('io', 1),))
            with self.assertRaises(FrozenInstanceError):
                result.status = 0
            with self.assertRaises(FrozenInstanceError):
                result.cleanup.lease_retained = True
            owner._cleanup_failures.clear()
            self.assertEqual(result.cleanup.categories, (('io', 1),))
            self.assertIs(scope.result(owner), result)
            self.assertIs(result.error, scope.outcome.error)

    def test_single_invocation_preserves_original_exception_identity(self):
        for error in (Cancelled(15), KeyboardInterrupt(), SystemExit(7)):
            with self.subTest(error=type(error).__name__), CliSignalScope() as scope:
                operation = Mock(side_effect=error)
                outcome = scope.execute(operation)
                self.assertIs(outcome.error, error)
                with self.assertRaises(FrozenInstanceError):
                    outcome.error = RuntimeError('replacement')
                with self.assertRaises(RuntimeError):
                    scope.execute(operation)
                operation.assert_called_once()

    def test_context_is_restored_after_preflight_failure(self):
        self.assertIsNone(current_cancellation())
        with self.scenario('local') as (_, tree, _, _, patches):
            error = ValueError('synthetic configuration failure')
            patches['load'].side_effect = error
            with self.assertRaises(ValueError) as raised:
                self.cli()
            self.assertIs(raised.exception, error)
            tree.start.assert_not_called()
        self.assertIsNone(current_cancellation())


if __name__ == '__main__':
    unittest.main()
