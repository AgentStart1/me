"""State transitions and recovery failures without touching an existing VM."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import vm_lifecycle
module = vm_lifecycle.state_module


class StateTests(unittest.TestCase):
    def state(self, root, name='fixture'):
        (root / 'vms').mkdir(exist_ok=True)
        return module.State(SimpleNamespace(name=name, owner=os.getpid(), native_owner=True,
            vm_dir=str(root / 'vms'), run_dir=str(root / 'run'),
            active_lock=str(root / 'run/active-vm.lock'), state_guard=str(root / 'run/vm-state.guard')))

    def test_operation_token_and_interrupted_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state = self.state(Path(directory))
            state.begin('owner')
            state.end('wrong')
            self.assertTrue(state.operation.exists())
            with self.assertRaises(module.StateError):
                state.begin('competitor')
            state.end('owner')
            self.assertFalse(state.operation.exists())
            state.guard_dir.mkdir()
            (state.guard_dir / 'owner.pid').write_text('99999999')
            with patch.object(module, 'running', return_value=False), self.assertRaises(module.StateError):
                state.acquire()
            self.assertTrue(state.guard_dir.exists())

    def test_network_state_blocks_takeover_and_unknown_probe_preserves_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state = self.state(Path(directory))
            state.acquire()
            helper = state.vms / 'fixture.gvproxy.pid'
            helper.write_text('{}')
            with self.assertRaises(module.StateError):
                self.state(Path(directory), 'other').acquire()
            with self.assertRaises(module.StateError):
                state.clear()
            helper.unlink()
            state.pid_path.write_text('123')
            state.identity_path.write_text(json.dumps({'pid': 123, 'shell_pid': 123, 'identity': ['fixture', 1]}))
            with patch.object(module, 'identity', side_effect=OSError('inspection failed')), self.assertRaises(OSError):
                state.clear()
            self.assertTrue(state.pid_path.exists())
            self.assertTrue(state.identity_path.exists())
            self.assertTrue(state.active.exists())

    def test_registration_failure_keeps_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            state = self.state(Path(directory))
            state.acquire()
            with patch.object(module.qemu, 'probe', return_value=None), self.assertRaises(module.StateError):
                state.register(123)
            self.assertTrue(state.active.exists())
            self.assertFalse(state.pid_path.exists())
            self.assertFalse(state.guard_dir.exists())

    def test_unknown_active_metadata_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            state = self.state(Path(directory))
            state.active.mkdir(parents=True)
            (state.active / 'unknown').write_text('retain')
            with self.assertRaises(module.StateError):
                state.acquire()
            self.assertEqual((state.active / 'unknown').read_text(), 'retain')

    def lifecycle(self, state):
        lifecycle = vm_lifecycle.Lifecycle.__new__(vm_lifecycle.Lifecycle)
        lifecycle.state = state
        lifecycle.child = None
        lifecycle.args = SimpleNamespace(force='true', stop_timeout='0')
        lifecycle.step = Mock()
        return lifecycle

    def test_partial_pid_publication_failed_cleanup_then_recovery(self):
        record = {'pid': 456, 'shell_pid': 123, 'identity': ['fixture-qemu', 1]}
        for boundary in ('identity', 'vm-pid', 'global-pid'):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as directory:
                state = self.state(Path(directory))
                state.acquire()
                state.prepare_launch()
                (state.active / 'launch.pid').write_text('123')
                failed_path = state.pid_path if boundary == 'vm-pid' else state.active / 'qemu.pid'
                atomic = module.atomic_text
                def publish(path, value):
                    if path == failed_path:
                        raise OSError('synthetic PID publication failure')
                    atomic(path, value)
                with patch.object(module.qemu, 'probe', return_value=record):
                    if boundary == 'identity':
                        with patch.object(module, 'write_record', side_effect=OSError('synthetic identity publication failure')):
                            with self.assertRaises(OSError):
                                state.register(123)
                    else:
                        with patch.object(module, 'atomic_text', side_effect=publish), self.assertRaises(OSError):
                            state.register(123)
                lifecycle = self.lifecycle(state)
                # Failed cleanup must preserve every published byte and networking.
                before = {p: p.read_bytes() for p in Path(directory).rglob('*') if p.is_file()}
                with patch.object(module.qemu, 'probe', return_value=record), \
                     patch.object(module, 'identity', return_value=record['identity']), \
                     patch.object(vm_lifecycle, 'terminate', side_effect=OSError('synthetic termination failure')):
                    with self.assertRaises(OSError):
                        lifecycle.stop_owned()
                    with self.assertRaises(module.StateError):
                        self.state(Path(directory), 'other').acquire()
                    with self.assertRaises(module.StateError):
                        state.clear()
                    with self.assertRaises(module.StateError):
                        state.release()
                self.assertEqual(before, {p: p.read_bytes() for p in Path(directory).rglob('*') if p.is_file()})
                lifecycle.step.assert_not_called()
                # A later stop can recover through launch.pid/native identity,
                # even when neither published PID pointer exists.
                alive = True
                def terminate(owned):
                    nonlocal alive
                    self.assertEqual(owned, record)
                    alive = False
                with patch.object(module.qemu, 'probe', side_effect=lambda *_: record if alive else None), \
                     patch.object(module, 'identity', side_effect=lambda *_: record['identity'] if alive else None), \
                     patch.object(module, 'running', return_value=False), \
                     patch.object(state, 'launcher_running', return_value=False), \
                     patch.dict(os.environ, FORCE='true'), \
                     patch.object(vm_lifecycle, 'terminate', side_effect=terminate) as termination:
                    lifecycle.stop()
                termination.assert_called_once_with(record)
                lifecycle.step.assert_called_once_with('network-stop')
                self.assertFalse(state.active.exists())
                self.assertFalse(state.pid_path.exists())
                self.assertFalse(state.identity_path.exists())

    def test_unknown_pending_process_blocks_stop_and_cross_vm_takeover(self):
        for unknown in ('probe-error', 'unrelated-live', 'missing-publication'):
            with self.subTest(unknown=unknown), tempfile.TemporaryDirectory() as directory:
                state = self.state(Path(directory))
                state.acquire()
                state.prepare_launch()
                if unknown != 'missing-publication':
                    (state.active / 'launch.pid').write_text('123')
                lifecycle = self.lifecycle(state)
                before = {p: p.read_bytes() for p in Path(directory).rglob('*') if p.is_file()}
                with patch.object(module.qemu, 'probe', side_effect=OSError('inspection failed') if unknown == 'probe-error' else None, return_value=None), \
                     patch.object(module, 'running', return_value=True), \
                     patch.object(state, 'launcher_running', return_value=False), \
                     patch.object(vm_lifecycle, 'terminate') as termination:
                    for operation in (lifecycle.stop, state.clear, state.release, self.state(Path(directory), 'other').acquire):
                        with self.assertRaises((OSError, module.StateError)):
                            operation()
                self.assertEqual(before, {p: p.read_bytes() for p in Path(directory).rglob('*') if p.is_file()})
                lifecycle.step.assert_not_called()
                termination.assert_not_called()

    def test_partial_identity_pid_reuse_never_signals_unrelated_process(self):
        with tempfile.TemporaryDirectory() as directory:
            state = self.state(Path(directory))
            state.acquire()
            state.identity_path.write_text(json.dumps({'pid': 456, 'shell_pid': 123, 'identity': ['old-qemu', 1]}))
            (state.active / 'launch.pid').write_text('123')
            lifecycle = self.lifecycle(state)
            with patch.object(module, 'identity', return_value=['unrelated', 2]), \
                 patch.object(state, 'launcher_running', return_value=False), \
                 patch.object(vm_lifecycle, 'terminate') as termination:
                lifecycle.stop()
            termination.assert_not_called()
            self.assertFalse(state.active.exists())

    def test_identity_alone_protects_live_process_without_pid_pointers(self):
        with tempfile.TemporaryDirectory() as directory:
            state = self.state(Path(directory))
            state.acquire()
            record = {'pid': 456, 'shell_pid': 123, 'identity': ['fixture-qemu', 1]}
            state.identity_path.write_text(json.dumps(record))
            with patch.object(module, 'identity', return_value=record['identity']):
                self.assertEqual(state.process_record(), record)
                for operation in (state.clear, state.release, self.state(Path(directory), 'other').acquire):
                    with self.assertRaises(module.StateError):
                        operation()
            self.assertTrue(state.identity_path.exists())
            self.assertTrue(state.active.exists())


if __name__ == '__main__':
    unittest.main()
