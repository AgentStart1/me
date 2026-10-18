"""Lifecycle transition and failure matrix using private state and synthetic processes."""
import contextlib
import io
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import vm_lifecycle as lifecycle
from vm_phase import Phase, Snapshot, TRANSITIONS, NoProcess, UnknownProcess, LaunchedProcess, OwnedProcess

state_module = lifecycle.state_module
RECORD = {'pid': 456, 'shell_pid': 123, 'identity': ['synthetic-qemu', 1]}


def evidence(phase):
    if phase == Phase.SPAWNING:
        return UnknownProcess()
    if phase == Phase.LAUNCHED:
        return LaunchedProcess(123)
    if phase in (Phase.REGISTERED, Phase.READY, Phase.STOPPING, Phase.RECOVERY):
        return OwnedProcess.from_record(RECORD)
    return NoProcess()


def cancel():
    # Exercise the installed handler, including deferred creation boundaries,
    # without sending a console event to any other test or process.
    signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)


class TransitionTests(unittest.TestCase):
    def test_all_legal_and_illegal_phase_pairs_and_roundtrips(self):
        for source in Phase:
            snapshot = Snapshot('reservation', source, evidence(source))
            self.assertEqual(Snapshot.from_data(snapshot.data()), snapshot)
            for target in Phase:
                with self.subTest(source=source, target=target):
                    if target in TRANSITIONS[source] or target == Phase.RECOVERY:
                        updated = snapshot.transition(target, evidence(target))
                        self.assertEqual(updated.generation, snapshot.generation)
                        self.assertEqual(updated.phase, target)
                        self.assertEqual(snapshot.phase, source)
                    else:
                        with self.assertRaises(ValueError):
                            snapshot.transition(target, evidence(target))

    def test_phase_requires_its_process_evidence(self):
        for phase in (Phase.RESERVED, Phase.NETWORK_STARTING, Phase.NETWORK_READY):
            with self.subTest(phase=phase), self.assertRaises(ValueError):
                Snapshot('reservation', phase, OwnedProcess.from_record(RECORD))
        for phase in (Phase.SPAWNING, Phase.LAUNCHED, Phase.REGISTERED, Phase.READY):
            with self.subTest(phase=phase), self.assertRaises(ValueError):
                Snapshot('reservation', phase, NoProcess())
        for pid in (0, -1, True, '123', 2**32):
            with self.subTest(pid=pid), self.assertRaises(ValueError):
                LaunchedProcess(pid)

    def test_transitions_cannot_discard_or_replace_process_evidence(self):
        launched = Snapshot('reservation', Phase.LAUNCHED, LaunchedProcess(123))
        other = OwnedProcess(124, 457, 'unrelated-qemu', 2)
        with self.assertRaises(ValueError):
            launched.transition(Phase.REGISTERED, other)
        owned = Snapshot('reservation', Phase.REGISTERED, OwnedProcess.from_record(RECORD))
        with self.assertRaises(ValueError):
            owned.transition(Phase.STOPPING, other)
        with self.assertRaises(ValueError):
            owned.transition(Phase.RECOVERY, NoProcess())
        unknown = Snapshot('reservation', Phase.SPAWNING, UnknownProcess())
        with self.assertRaises(ValueError):
            unknown.transition(Phase.STOPPING, NoProcess())


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        vms = self.root / 'vms'
        vms.mkdir()
        self.state = state_module.State(SimpleNamespace(name='fixture', owner=os.getpid(), native_owner=True,
            vm_dir=str(vms), run_dir=str(self.root / 'run'), active_lock=str(self.root / 'run/active-vm.lock'),
            state_guard=str(self.root / 'run/vm-state.guard')))
        self.home = vms / 'fixture'
        self.home.mkdir()
        self.disk = self.home / 'disk.qcow2'
        self.disk.write_bytes(b'untouched synthetic disk')
        (self.home / 'ready').touch()
        self.helper = vms / 'fixture.gvproxy.pid'
        self.alive = False
        self.events = []
        self.phases = []
        self.x = self.controller()
        stack = self.enterContext(contextlib.ExitStack())
        stack.enter_context(patch.object(state_module.qemu, 'probe', side_effect=lambda *_: RECORD if self.alive else None))
        stack.enter_context(patch.object(state_module, 'identity', side_effect=lambda p: RECORD['identity'] if p == RECORD['pid'] and self.alive else None))
        stack.enter_context(patch.object(state_module, 'running', side_effect=lambda p: str(p) == '123' and self.alive))
        stack.enter_context(patch.object(lifecycle, 'terminate', side_effect=self.terminate))
        stack.enter_context(patch.object(lifecycle.subprocess, 'Popen', side_effect=self.spawn))
        writer = state_module.write_record
        def write(path, value):
            if path == self.state.snapshot_path:
                self.phases.append(Phase(value['phase']))
            writer(path, value)
        stack.enter_context(patch.object(state_module, 'write_record', side_effect=write))
        stack.enter_context(patch.object(self.state, 'launcher_running', return_value=False))
        self.handlers = {n: signal.getsignal(n) for n in state_module.signals()}
        for number in self.handlers:
            signal.signal(number, lambda n, _f: (_ for _ in ()).throw(state_module.Cancelled(n)))
        self.addCleanup(self.restore_handlers)

    def restore_handlers(self):
        for number, handler in self.handlers.items():
            signal.signal(number, handler)

    def controller(self):
        x = lifecycle.Lifecycle.__new__(lifecycle.Lifecycle)
        x.state = self.state
        x.home = self.home
        x.child = None
        x.pending_controller = None
        x.owned = None
        x.token = 'synthetic-operation'
        x.profile = 'unused'
        x.bash = 'unused'
        x.adapter = 'unused'
        x.args = SimpleNamespace(force='true', stop_timeout='0', boot_timeout='1')
        x.step = Mock(return_value=json.dumps(['synthetic-qemu']))
        x.network = Mock(side_effect=self.network)
        x.wait_ready = Mock()
        return x

    def network(self, action):
        self.events.append('network-' + action)
        if action == 'start':
            self.helper.write_text('synthetic helper ownership')
        elif action == 'stop':
            self.helper.unlink(missing_ok=True)

    def spawn(self, *_args, **_kwargs):
        self.events.append('spawn')
        self.alive = True
        (self.state.active / 'launch.pid').write_text('123')
        child = Mock()
        child.poll.side_effect = lambda: None if self.alive else 0
        child.wait.side_effect = lambda **_: self.events.append('join-adapter')
        return child

    def terminate(self, record):
        self.assertEqual(record, RECORD)
        self.events.append('terminate-qemu')
        self.alive = False

    def execute(self, action='start', controller=None):
        with contextlib.redirect_stderr(io.StringIO()):
            return (controller or self.x).execute(action)

    def assert_clean(self):
        self.assertFalse(self.state.active.exists())
        self.assertFalse(self.state.operation.exists())
        self.assertFalse(self.state.guard_dir.exists())
        self.assertFalse(self.state.pid_path.exists())
        self.assertFalse(self.state.identity_path.exists())
        self.assertFalse(self.helper.exists())
        self.assertFalse(self.alive)
        self.assertEqual(self.disk.read_bytes(), b'untouched synthetic disk')

    def test_success_and_ordered_shutdown(self):
        self.assertEqual(self.execute(), 0)
        self.assertEqual(self.state.snapshot().phase, Phase.READY)
        self.assertEqual(self.phases, [Phase.RESERVED, Phase.NETWORK_STARTING, Phase.NETWORK_READY,
            Phase.SPAWNING, Phase.LAUNCHED, Phase.REGISTERED, Phase.READY])
        self.assertFalse(self.state.operation.exists())
        self.assertEqual(self.execute('stop', self.controller()), 0)
        self.assertEqual(self.events, ['network-start', 'spawn', 'terminate-qemu', 'network-stop'])
        self.assert_clean()

    def test_plan_failure_never_takes_ownership(self):
        self.x.step.side_effect = OSError('synthetic plan failure')
        self.assertEqual(self.execute(), 1)
        self.assertEqual(self.events, [])
        self.assert_clean()

    def test_signal_after_acquire_is_delivered_after_ownership_assignment(self):
        acquire = self.state.acquire
        def acquired():
            value = acquire()
            cancel()
            return value
        with patch.object(self.state, 'acquire', side_effect=acquired):
            self.assertEqual(self.execute(), 128 + signal.SIGTERM)
        self.assertEqual(self.events, ['network-stop'])
        self.assertNotIn(Phase.SPAWNING, self.phases)
        self.assert_clean()

    def test_signal_at_completed_lease_publication_releases_the_lease(self):
        begin = self.state.begin
        def begun(token):
            begin(token)
            cancel()
        with patch.object(self.state, 'begin', side_effect=begun):
            self.assertEqual(self.execute(), 128 + signal.SIGTERM)
        self.assertEqual(self.events, [])
        self.assert_clean()

    def test_signal_during_nested_guard_release_is_not_lost(self):
        release = self.state.release_guard
        delivered = False
        def released(token):
            nonlocal delivered
            release(token)
            if not delivered:
                delivered = True
                cancel()
        with patch.object(self.state, 'release_guard', side_effect=released):
            self.assertEqual(self.execute(), 128 + signal.SIGTERM)
        self.assertTrue(delivered)
        self.assertEqual(self.events, [])
        self.assert_clean()

    def test_network_failure_and_cancel_clean_only_owned_network(self):
        for error in (OSError('synthetic network failure'), state_module.Cancelled(signal.SIGTERM)):
            with self.subTest(error=error):
                self.x = self.controller()
                def network(action):
                    self.network(action)
                    if action == 'start':
                        raise error
                self.x.network.side_effect = network
                self.assertEqual(self.execute(), 1 if isinstance(error, OSError) else 128 + signal.SIGTERM)
                self.assertNotIn(Phase.SPAWNING, self.phases)
                self.assert_clean()

    def test_log_open_failure_is_before_process_creation(self):
        (self.home / 'qemu.log').mkdir()
        self.assertEqual(self.execute(), 1)
        self.assertEqual(self.events, ['network-start', 'network-stop'])
        self.assertNotIn(Phase.SPAWNING, self.phases)
        self.assert_clean()

    def test_cancel_before_log_open_does_not_mark_creation_unknown(self):
        original = Path.open
        def opened(path, *args, **kwargs):
            if path == self.home / 'qemu.log':
                cancel()
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', opened):
            self.assertEqual(self.execute(), 128 + signal.SIGTERM)
        self.assertNotIn(Phase.SPAWNING, self.phases)
        self.assert_clean()

    def test_definitive_spawn_failure_rolls_back_before_cleanup(self):
        with patch.object(lifecycle.subprocess, 'Popen', side_effect=OSError('synthetic spawn failure')):
            self.assertEqual(self.execute(), 1)
        spawning = self.phases.index(Phase.SPAWNING)
        self.assertEqual(self.phases[spawning + 1], Phase.NETWORK_READY)
        self.assertEqual(self.events, ['network-start', 'network-stop'])
        self.assert_clean()

    def test_signal_during_spawn_assigns_and_joins_handle_before_release(self):
        def spawn(*args, **kwargs):
            child = self.spawn(*args, **kwargs)
            cancel()
            return child
        with patch.object(lifecycle.subprocess, 'Popen', side_effect=spawn):
            self.assertEqual(self.execute(), 128 + signal.SIGTERM)
        self.assertEqual(self.events[-3:], ['terminate-qemu', 'join-adapter', 'network-stop'])
        self.assert_clean()

    def test_definitive_spawn_failure_with_pending_signal_still_rolls_back(self):
        def spawn(*_args, **_kwargs):
            cancel()
            raise OSError('synthetic spawn failure')
        with patch.object(lifecycle.subprocess, 'Popen', side_effect=spawn):
            self.assertEqual(self.execute(), 128 + signal.SIGTERM)
        self.assert_clean()

    def test_publication_failure_at_every_boundary_is_recoverable(self):
        boundaries = ('reserved', 'network-starting', 'network-ready', 'spawning',
                      'launched', 'registered', 'identity', 'vm-pid', 'global-pid', 'ready')
        for boundary in boundaries:
            with self.subTest(boundary=boundary):
                self.x = self.controller()
                writer, atomic = state_module.write_record, state_module.atomic_text
                failed = False
                def fail_once(path, value):
                    nonlocal failed
                    phase = value.get('phase') if isinstance(value, dict) else None
                    target = ((path == self.state.snapshot_path and phase == boundary) or
                        (boundary == 'identity' and path == self.state.identity_path) or
                        (boundary == 'vm-pid' and path == self.state.pid_path) or
                        (boundary == 'global-pid' and path == self.state.active / 'qemu.pid'))
                    if target and not failed:
                        failed = True
                        raise OSError('synthetic publication failure')
                    return (writer if isinstance(value, dict) else atomic)(path, value)
                with patch.object(state_module, 'write_record', side_effect=fail_once), \
                     patch.object(state_module, 'atomic_text', side_effect=fail_once):
                    self.assertEqual(self.execute(), 1)
                self.assertTrue(failed)
                self.assert_clean()

    def test_initial_lease_and_reservation_metadata_failures_roll_back_only_new_directories(self):
        targets = [self.state.operation / name for name in ('owner.pid', 'token', 'vm-name')]
        targets += [self.state.active / name for name in ('vm-name', 'launcher.pid', 'launcher-native')]
        for target in targets:
            with self.subTest(target=target):
                self.x = self.controller()
                atomic = state_module.atomic_text
                def write(path, value):
                    if path == target:
                        raise OSError('synthetic initial publication failure')
                    return atomic(path, value)
                with patch.object(state_module, 'atomic_text', side_effect=write):
                    self.assertEqual(self.execute(), 1)
                self.assert_clean()

    def test_new_guard_metadata_failure_rolls_back_and_allows_retry(self):
        for name in ('owner.pid', 'native-owner', 'token'):
            for after_write in (False, True):
                with self.subTest(name=name, after_write=after_write):
                    atomic = state_module.atomic_text
                    def write(path, value):
                        if path == self.state.guard_dir / name:
                            if after_write:
                                atomic(path, value)
                            raise OSError('synthetic guard publication failure')
                        return atomic(path, value)
                    with patch.object(state_module, 'atomic_text', side_effect=write):
                        self.assertEqual(self.execute(), 1)
                    self.assert_clean()
                    self.state.begin('retry')
                    self.state.end('retry')
                    self.assert_clean()

    def test_guard_write_failure_with_pending_cancel_completes_rollback(self):
        atomic = state_module.atomic_text
        def write(path, value):
            if path == self.state.guard_dir / 'token':
                cancel()
                raise OSError('synthetic guard publication failure')
            return atomic(path, value)
        with patch.object(state_module, 'atomic_text', side_effect=write):
            self.assertEqual(self.execute(), 128 + signal.SIGTERM)
        self.assert_clean()
        self.state.begin('retry')
        self.state.end('retry')
        self.assert_clean()

    def test_existing_unknown_guard_is_never_removed_by_acquisition(self):
        self.state.guard_dir.mkdir(parents=True)
        marker = self.state.guard_dir / 'retain'
        marker.write_text('preexisting ownership')
        with patch.object(state_module.time, 'monotonic', side_effect=[0, 10]):
            with self.assertRaises(state_module.StateError):
                self.state.begin('contender')
        self.assertEqual(marker.read_text(), 'preexisting ownership')
        self.assertFalse(self.state.operation.exists())

    def test_standalone_guard_creation_cancel_rolls_back_before_handoff(self):
        original_mkdir = Path.mkdir
        atomic = state_module.atomic_text
        for boundary in ('mkdir', 'owner.pid', 'native-owner', 'token'):
            with self.subTest(boundary=boundary):
                def mkdir(path, *args, **kwargs):
                    value = original_mkdir(path, *args, **kwargs)
                    if path == self.state.guard_dir and boundary == 'mkdir':
                        cancel()
                    return value
                def write(path, value):
                    atomic(path, value)
                    if path == self.state.guard_dir / boundary:
                        cancel()
                with patch.object(Path, 'mkdir', mkdir), \
                     patch.object(state_module, 'atomic_text', side_effect=write):
                    with self.assertRaises(state_module.Cancelled):
                        self.state.acquire_guard()
                self.assert_clean()
                token = self.state.acquire_guard()
                self.state.release_guard(token)
                self.assert_clean()

    def test_readiness_failure_and_cancel_stop_verified_process_first(self):
        for error in (OSError('synthetic readiness failure'), state_module.Cancelled(signal.SIGTERM)):
            with self.subTest(error=error):
                self.x = self.controller()
                self.x.wait_ready.side_effect = error
                self.assertEqual(self.execute(), 1 if isinstance(error, OSError) else 128 + signal.SIGTERM)
                self.assertEqual(self.events[-3:], ['terminate-qemu', 'join-adapter', 'network-stop'])
                self.assert_clean()

    def test_cancel_after_ready_commit_keeps_the_completed_vm(self):
        transition = self.state.transition
        def changed(generation, phase, process=None):
            value = transition(generation, phase, process)
            if phase == Phase.READY:
                cancel()
            return value
        with patch.object(self.state, 'transition', side_effect=changed):
            self.assertEqual(self.execute(), 128 + signal.SIGTERM)
        self.assertEqual(self.state.snapshot().phase, Phase.READY)
        self.assertTrue(self.alive)
        self.assertTrue(self.helper.exists())
        self.assertFalse(self.state.operation.exists())

    def test_failed_termination_retains_identity_network_and_can_retry(self):
        self.x.wait_ready.side_effect = OSError('synthetic readiness failure')
        with patch.object(lifecycle, 'terminate', side_effect=OSError('synthetic termination failure')):
            self.assertEqual(self.execute(), 1)
        self.assertEqual(self.state.snapshot().phase, Phase.RECOVERY)
        self.assertEqual(self.state.snapshot().process.record(), RECORD)
        self.assertTrue(self.helper.exists())
        self.assertTrue(self.alive)
        self.assertFalse(self.state.operation.exists())
        self.assertEqual(self.execute('stop', self.controller()), 0)
        self.assert_clean()

    def test_unknown_launch_retains_all_ownership_and_rejects_takeover(self):
        child = Mock()
        child.poll.return_value = 1
        with patch.object(lifecycle.subprocess, 'Popen', return_value=child):
            self.assertEqual(self.execute(), 1)
        self.assertEqual(self.state.snapshot().phase, Phase.RECOVERY)
        self.assertIsInstance(self.state.snapshot().process, UnknownProcess)
        self.assertTrue(self.helper.exists())
        self.assertFalse(self.state.operation.exists())
        self.assertEqual(self.execute('stop', self.controller()), 1)
        with self.assertRaises(state_module.StateError):
            self.state.acquire()

    def test_repeated_start_failure_does_not_clean_an_existing_vm(self):
        self.assertEqual(self.execute(), 0)
        borrower = self.controller()
        borrower.wait_ready.side_effect = OSError('synthetic health check failure')
        self.assertEqual(self.execute(controller=borrower), 1)
        self.assertTrue(self.alive)
        self.assertTrue(self.helper.exists())
        self.assertEqual(self.state.snapshot().phase, Phase.READY)
        self.assertFalse(self.state.operation.exists())

    def test_cancel_during_graceful_stop_preserves_vm_for_later_stop(self):
        self.assertEqual(self.execute(), 0)
        stopper = self.controller()
        stopper.args.force = 'false'
        stopper.step.side_effect = state_module.Cancelled(signal.SIGTERM)
        self.assertEqual(self.execute('stop', stopper), 128 + signal.SIGTERM)
        self.assertEqual(self.state.snapshot().phase, Phase.STOPPING)
        self.assertTrue(self.helper.exists())
        self.assertTrue(self.alive)
        self.assertFalse(self.state.operation.exists())
        self.assertEqual(self.execute('stop', self.controller()), 0)
        self.assert_clean()

    def test_cancel_during_reservation_teardown_finishes_the_atomic_guarded_update(self):
        self.assertEqual(self.execute(), 0)
        unlink = Path.unlink
        delivered = False
        def removed(path, *args, **kwargs):
            nonlocal delivered
            result = unlink(path, *args, **kwargs)
            if path == self.state.active / 'vm-name' and not delivered:
                delivered = True
                cancel()
            return result
        with patch.object(Path, 'unlink', removed):
            self.assertEqual(self.execute('stop', self.controller()), 128 + signal.SIGTERM)
        self.assertTrue(delivered)
        self.assert_clean()

    def test_late_generation_cannot_mutate_replacement_reservation(self):
        old = self.state.acquire()
        self.state.release()
        current = self.state.acquire()
        with self.assertRaises(state_module.StateError):
            self.state.transition(old.generation, Phase.NETWORK_STARTING)
        self.assertEqual(self.state.snapshot(), current)
        self.x.owned = old
        with self.assertRaises(state_module.StateError):
            self.x.stop_owned()
        self.assertEqual(self.state.snapshot(), current)
        self.assertEqual(self.events, [])

    def test_helper_controller_lock_alone_blocks_clear_and_takeover(self):
        self.state.acquire()
        guard = Path(str(self.helper) + '.control.lock')
        guard.mkdir()
        for action in (self.state.clear, self.state.release, self.state.acquire):
            with self.assertRaises(state_module.StateError):
                action()
        self.assertTrue(self.state.active.exists())
        self.assertTrue(guard.exists())

    def test_registration_retry_cannot_replace_native_identity(self):
        self.state.acquire()
        self.alive = True
        self.state.register(123)
        before = self.state.snapshot()
        with patch.object(state_module.qemu, 'probe', return_value=dict(RECORD, identity=['unrelated-qemu', 2])):
            with self.assertRaises(state_module.StateError):
                self.state.register(123)
        self.assertEqual(self.state.snapshot(), before)
        self.assertEqual(json.loads(self.state.identity_path.read_text()), RECORD)

    def test_stale_compatibility_files_are_removed_before_a_new_launch(self):
        self.state.pid_path.write_text('99999999')
        self.state.identity_path.write_text(json.dumps({'pid': 99999999, 'shell_pid': 99999999, 'identity': ['exited-qemu', 0]}))
        self.x.wait_ready.side_effect = OSError('synthetic readiness failure')
        self.assertEqual(self.execute(), 1)
        self.assert_clean()

    def test_preexisting_helper_without_a_reservation_is_not_adopted_or_stopped(self):
        self.helper.write_text('preexisting helper ownership')
        self.assertEqual(self.execute(), 1)
        self.assertEqual(self.helper.read_text(), 'preexisting helper ownership')
        self.assertEqual(self.events, [])
        self.assertFalse(self.state.active.exists())
        self.assertFalse(self.state.operation.exists())

    def test_provisioning_stop_and_keep_lock_reset_for_verification_boot(self):
        reserved = self.state.acquire()
        for keep in (True, False):
            self.state.prepare_launch()
            self.alive = True
            self.state.register(123)
            self.network('start')
            with patch.object(state_module, 'terminate', side_effect=self.terminate):
                self.state.stop_qemu()
            self.assertEqual(self.state.snapshot().phase, Phase.STOPPING)
            self.assertTrue(self.helper.exists())
            with self.assertRaises(state_module.StateError):
                self.state.clear(keep)
            self.network('stop')
            self.state.clear(keep)
            if keep:
                self.assertEqual(self.state.snapshot().phase, Phase.RESERVED)
                self.assertEqual(self.state.snapshot().generation, reserved.generation)
                self.assertIsInstance(self.state.snapshot().process, NoProcess)
        self.assert_clean()

    def test_unjoinable_native_controller_retains_lease_even_without_helper_state(self):
        child = Mock(pid=99999999)
        child.poll.return_value = None
        child.send_signal.side_effect = OSError('synthetic console signal failure')
        child.kill.side_effect = OSError('synthetic process termination failure')
        def spawn(*_args, **_kwargs):
            cancel()
            return child
        def network(action):
            if action == 'start':
                self.x.run_child(['unused'], 'network-start', native=True)
        self.x.network.side_effect = network
        with patch.object(lifecycle.subprocess, 'Popen', side_effect=spawn), \
             patch.object(lifecycle.os, 'killpg', create=True, side_effect=OSError('synthetic group signal failure')):
            self.assertEqual(self.execute(), 128 + signal.SIGTERM)
        self.assertTrue(self.state.active.exists())
        self.assertTrue(self.state.operation.exists())
        self.assertFalse(self.helper.exists())
        self.assertEqual(self.state.snapshot().phase, Phase.RECOVERY)
        with self.assertRaises(state_module.StateError):
            self.state.begin('competitor')


class ChildOwnershipTests(unittest.TestCase):
    def test_cancel_native_controller_joins_before_returning(self):
        child = Mock(pid=99999999)
        child.poll.return_value = None
        x = lifecycle.Lifecycle.__new__(lifecycle.Lifecycle)
        def spawn(*_args, **_kwargs):
            cancel()
            return child
        with patch.object(lifecycle.subprocess, 'Popen', side_effect=spawn), \
             patch.object(lifecycle.os, 'killpg', create=True) as killpg:
            with self.assertRaises(state_module.Cancelled):
                x.run_child(['unused'], 'network-start', native=True)
        if os.name == 'nt':
            child.send_signal.assert_called_once_with(signal.CTRL_BREAK_EVENT)
        else:
            killpg.assert_called_once_with(child.pid, signal.SIGTERM)
        child.wait.assert_called_once_with(timeout=5)

    def test_failed_graceful_cancel_still_kills_and_joins_controller(self):
        child = Mock(pid=99999999)
        child.poll.return_value = None
        child.send_signal.side_effect = OSError('synthetic console signal failure')
        x = lifecycle.Lifecycle.__new__(lifecycle.Lifecycle)
        def spawn(*_args, **_kwargs):
            cancel()
            return child
        with patch.object(lifecycle.subprocess, 'Popen', side_effect=spawn), \
             patch.object(lifecycle.os, 'killpg', create=True, side_effect=OSError('synthetic group signal failure')):
            with self.assertRaises(state_module.Cancelled):
                x.run_child(['unused'], 'network-start', native=True)
        child.kill.assert_called_once()
        child.wait.assert_called_once_with(timeout=5)


if __name__ == '__main__':
    unittest.main()
