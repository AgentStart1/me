"""Guest discovery, screen isolation and installer settings contracts."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import guest_registry
import guest_screen
import guest_seed
import guest_config
from macos_install import key_events, text_keys, press_keys, terminal_ready
from process_identity import identity
from windows_image import select as select_windows_image
spec = importlib.util.spec_from_file_location('guest_vm', ROOT / 'scripts/guest-vm.py')
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)


class GuestPanelTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        environment = patch.dict(os.environ, {'QEMU_GUESTS_REGISTRY_DIR': str(self.home / 'registry')})
        environment.start(); self.addCleanup(environment.stop)
        self.config = {'name': 'desktop', 'os': 'ubuntu', 'graphical': True, 'qmp_port': 23401,
                       'memory': 2048, 'cpus': 2, 'ssh_port': 23400, 'qemu_args': [],
                       'hardware_args': [], 'install_args': []}

    def test_status_without_guests_does_not_create_registry(self):
        self.assertEqual(guest_registry.snapshot(), {'state': 'available', 'items': []})
        self.assertFalse(guest_registry.directory().exists())

    def test_stopped_guest_preserves_config_without_leaking_state_paths(self):
        guest_registry.register(self.config, self.home)
        item = guest_registry.snapshot()['items'][0]
        self.assertEqual(item['state'], 'stopped')
        self.assertFalse(item['screenAvailable'])
        self.assertNotIn('state_dir', item)
        self.assertNotIn('qmp_port', item)

    def test_orphaned_qemu_is_recovery_required_not_ready(self):
        guest_registry.register(self.config, self.home)
        (self.home / 'running.json').write_text(json.dumps({'pid': os.getpid(), 'identity': identity(os.getpid()), 'token': 'old', 'phase': 'ready'}))
        lease = self.home / 'session.lock'; lease.mkdir()
        (lease / 'owner.json').write_text(json.dumps({'pid': os.getpid(), 'identity': identity(os.getpid()), 'token': 'different'}))
        item = guest_registry.snapshot()['items'][0]
        self.assertEqual(item['state'], 'recovery-required')
        self.assertFalse(item['screenAvailable'])

    def test_unknown_screen_id_cannot_select_a_host_endpoint(self):
        with self.assertRaises(ValueError):
            guest_screen.capture('../../localhost:1234')

    def test_headless_guest_has_no_screen_endpoint(self):
        config = {**self.config, 'graphical': False}
        command = vm.arguments(config, self.home, False)
        self.assertNotIn('-qmp', command)

    def test_graphical_guest_uses_loopback_qmp(self):
        command = vm.arguments(self.config, self.home, False)
        self.assertIn('tcp:127.0.0.1:23401,server=on,wait=off', command)

    def test_recovery_keyboard_input_is_ordered_and_fixed_command_only(self):
        events = key_events(['shift', 'meta_l', 't'])
        self.assertEqual([event['data']['down'] for event in events], [True]*3 + [False]*3)
        self.assertEqual(events[-1]['data']['key']['data'], 'shift')
        self.assertEqual(text_keys('sh /Volumes/GUESTSEED/macos-install.sh\n')[-1], ['ret'])
        with self.assertRaises(ValueError):
            text_keys('$(unsafe)')

    def test_recovery_releases_modifiers_even_when_press_wait_is_interrupted(self):
        client = Mock()
        with patch('macos_install.time.sleep', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                press_keys(client, ['shift', 'a'])
        pressed = client.execute.call_args_list[0].args[1]['events']
        released = client.execute.call_args_list[1].args[1]['events']
        self.assertTrue(all(event['data']['down'] for event in pressed))
        self.assertTrue(all(not event['data']['down'] for event in released))
        self.assertEqual([event['data']['key']['data'] for event in released], ['a', 'shift'])

    def test_terminal_window_title_does_not_authorize_installer_handoff(self):
        self.assertFalse(terminal_ready('Terminal Shell Edit View Window Help'))
        self.assertFalse(terminal_ready('Terminal — bash — 80x24'))
        self.assertTrue(terminal_ready('-bash-3.2#'))
        self.assertTrue(terminal_ready('-bash-3.2 #'))

    def test_macos_seed_uses_explicit_target_and_bootstrap_product(self):
        package = self.home / 'bootstrap.pkg'; package.write_bytes(b'fixture package')
        config = {**self.config, 'os': 'macos', 'macos': {'bootstrap_package': str(package),
                  'target_disk': '/dev/disk0', 'installer_app': '/Volumes/Install macOS/Install macOS.app'}}
        guest_seed.prepare_seed(config, self.home / 'seed')
        script = (self.home / 'seed/macos-install.sh').read_text()
        self.assertIn('target=/dev/disk0', script)
        self.assertIn('--installpackage', script)
        self.assertIn('refusing unattended erase', script)
        self.assertEqual((self.home / 'seed/bootstrap.pkg').read_bytes(), b'fixture package')
        self.assertFalse((self.home / 'seed/payload.zip').exists())

    def test_windows_variant_selection_uses_installation_type_not_display_suffix(self):
        editions = [{'name': 'Windows Server 2025 SERVERSTANDARDCORE', 'type': 'Server Core'},
                    {'name': 'Windows Server 2025 SERVERSTANDARD', 'type': 'Server'}]
        for graphical, expected in [(True, editions[1]['name']), (False, editions[0]['name'])]:
            with self.subTest(graphical=graphical):
                self.assertEqual(select_windows_image(editions, 'Windows Server 2025 SERVERSTANDARD', graphical), expected)

    def test_windows_client_headless_selection_fails_without_core_variant(self):
        with self.assertRaisesRegex(ValueError, 'no matching'):
            select_windows_image([{'name': 'Windows 10 Pro', 'type': 'Client'}], 'Windows 10 Pro', False)

    def test_live_qemu_screen_capture_verifies_identity_and_removes_temp_frame(self):
        import shutil
        qemu = shutil.which('qemu-system-x86_64')
        if not qemu:
            self.skipTest('Native QEMU required')
        with socket.socket() as port:
            port.bind(('127.0.0.1', 0)); number = port.getsockname()[1]
        config = {**self.config, 'qmp_port': number}
        identifier = guest_registry.register(config, self.home)
        with open(self.home / 'qemu.log', 'wb') as log:
            child = subprocess.Popen([qemu, '-S', '-accel', 'tcg', '-m', '64', '-display', 'none', '-monitor', 'none',
                                     '-qmp', f'tcp:127.0.0.1:{number},server=on,wait=off'], stdout=log, stderr=log)
            self.addCleanup(lambda: child.poll() is None and child.kill())
            try:
                token = 'screen-test'
                record = {'pid': child.pid, 'identity': identity(child.pid), 'token': token, 'phase': 'paused'}
                (self.home / 'running.json').write_text(json.dumps(record))
                lease = self.home / 'session.lock'; lease.mkdir()
                (lease / 'owner.json').write_text(json.dumps({'pid': os.getpid(), 'identity': identity(os.getpid()), 'token': token}))
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    try:
                        frame = guest_screen.capture(identifier)
                        break
                    except (OSError, ValueError):
                        time.sleep(.1)
                else:
                    self.fail('Native QEMU screen was unavailable')
                self.assertTrue(base64.b64decode(frame['data']).startswith(b'\x89PNG'))
                item = guest_registry.snapshot()['items'][0]
                self.assertEqual(item['state'], 'paused')
                self.assertTrue(item['screenAvailable'])
                self.assertFalse(list(self.home.glob('screen-*')))
            finally:
                child.terminate(); child.wait(timeout=10)

    def test_screen_capture_refuses_another_process_listener(self):
        identifier = guest_registry.register(self.config, self.home)
        record = {'pid': os.getpid(), 'identity': identity(os.getpid())}
        with patch.object(guest_screen, 'state', return_value=('booting', record)), \
             patch.object(guest_screen, 'owns_listeners', return_value=False):
            with self.assertRaisesRegex(ValueError, 'does not belong'):
                guest_screen.capture(identifier)


if __name__ == '__main__':
    unittest.main()
