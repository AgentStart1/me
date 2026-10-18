"""State transitions and recovery failures without touching an existing VM."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('vm_state_controller', SCRIPTS / 'vm-state.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


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


if __name__ == '__main__':
    unittest.main()
