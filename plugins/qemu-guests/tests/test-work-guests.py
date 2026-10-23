"""Work-guest media, forwarding, concurrency and cancellation contracts."""
import importlib.util
import io
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import guest_config
import guest_seed
spec = importlib.util.spec_from_file_location('guest_vm', SCRIPTS / 'guest-vm.py')
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)


class GuestTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.registry = patch.dict(os.environ, {'QEMU_GUESTS_REGISTRY_DIR': str(self.root / 'registry')})
        self.registry.start()
        self.addCleanup(self.registry.stop)
        for name, content in [('access', b'private fixture'), ('access.pub', b'ssh-ed25519 AAAA fixture'),
                              ('runtime.zip', b'runtime fixture'), ('base', b'image fixture')]:
            (self.root / name).write_bytes(content)
        self.profile = self.root / 'guest.json'
        with zipfile.ZipFile(self.root / 'runtime.zip', 'w') as archive:
            archive.writestr('runtime.json', json.dumps({'platform': 'linux', 'arch': 'x64'}))
        self.data = {'name': 'work', 'os': 'ubuntu', 'state_dir': 'state', 'base_image': 'base',
                     'media_sha256': hashlib.sha256(b'image fixture').hexdigest(),
                     'access_key': 'access', 'ssh_port': 2230,
                     'appium': {'host_port': 24730, 'runtime_archive': 'runtime.zip', 'sha256': hashlib.sha256((self.root / 'runtime.zip').read_bytes()).hexdigest()}}

    def config(self, **changes):
        self.profile.write_text(json.dumps({**self.data, **changes}))
        return guest_config.load(self.profile)

    def test_appium_tunnel_is_authenticated_loopback_only(self):
        spec = importlib.util.spec_from_file_location('connect_appium', SCRIPTS / 'connect-appium.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        args = module.command(self.config())
        self.assertEqual(args[args.index('-L') + 1], '127.0.0.1:24730:127.0.0.1:4723')
        self.assertIn('ExitOnForwardFailure=yes', args)
        self.assertNotIn('StrictHostKeyChecking=no', args)
        self.assertEqual(args[-1], 'developer@127.0.0.1')

    def test_acceptance_polls_cloud_init_without_orphan_waiters(self):
        command = vm.acceptance(self.config(), self.root)
        self.assertNotIn('--wait', command[-1])
        self.assertIn('status --format=json', command[-1])
        self.assertIn('StrictHostKeyChecking=accept-new', command)
        self.assertIn('UserKnownHostsFile=' + str(self.root / 'known_hosts'), command)

    def test_unknown_configuration_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            self.config(typo=True)

    def test_overlapping_appium_ssh_port_rejected(self):
        with self.assertRaisesRegex(ValueError, 'collide'):
            self.config(appium={**self.data['appium'], 'host_port': 2230})

    def test_checksum_failure_precedes_disk_creation(self):
        config = self.config(media_sha256='0' * 64)
        home = self.root / 'state'
        home.mkdir()
        with patch.object(vm.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'checksum'):
                vm.initialize(config, home)
            run.assert_not_called()
        self.assertFalse((home / 'disk.qcow2').exists())

    def test_ubuntu_seed_iso_contains_cloud_init_and_appium(self):
        config = self.config()
        seed = self.root / 'seed'
        guest_seed.prepare_seed(config, seed)
        import pycdlib
        iso = pycdlib.PyCdlib()
        iso.open(str(self.root / 'seed.iso'))
        self.addCleanup(iso.close)
        data = io.BytesIO()
        iso.get_file_from_iso_fp(data, joliet_path='/user-data')
        cloud = json.loads(data.getvalue().decode().split('\n', 1)[1])
        self.assertFalse(cloud['ssh_pwauth'])
        self.assertEqual(cloud['runcmd'], [['bash', '/opt/qemu-guests/seed-bootstrap.sh']])
        self.assertTrue(any(f['path'].endswith('/seed-bootstrap.sh') for f in cloud['write_files']))
        self.assertFalse(any(f['path'].endswith('/appium-runtime.zip') for f in cloud['write_files']))
        self.assertTrue(all(f['permissions'] == '0600' for f in cloud['write_files']))

    def test_windows_seed_contains_unattended_setup_and_bootstrap(self):
        config = self.config()
        config['installer_iso'] = config.pop('base_image')
        config['os'] = 'windows'
        config['graphical'] = True
        config['qmp_port'] = 2241
        seed = self.root / 'seed'
        guest_seed.prepare_seed(config, seed)
        root = ET.parse(seed / 'Autounattend.xml').getroot()
        self.assertEqual(root.tag, '{urn:schemas-microsoft-com:unattend}unattend')
        with zipfile.ZipFile(seed / 'payload.zip') as archive:
            bootstrap = archive.read('bootstrap.ps1').decode()
            self.assertIn('Register-ScheduledTask', bootstrap)
            self.assertIn('Set-NetFirewallRule -Name OpenSSH-Server-In-TCP -Enabled True -Profile Any', bootstrap)
            self.assertIn('-LogonType Interactive', bootstrap)
            self.assertIn('appium-runtime.zip', archive.namelist())
            self.assertNotIn('backend-key', archive.namelist())
            self.assertNotIn('docker.exe', archive.namelist())
        command = vm.arguments(config, self.root, True)
        self.assertIn('order=c,once=d', command)
        self.assertTrue(any('index=2' in arg and 'base' in arg for arg in command))
        self.assertTrue(any('index=3' in arg and 'seed.iso' in arg for arg in command))

    def test_custom_guest_requires_explicit_unattended_adapter(self):
        with self.assertRaisesRegex(ValueError, 'no universal installer'):
            self.config(os='custom', graphical=False)

    @unittest.skipUnless(os.name == 'nt', 'PowerShell syntax validation is Windows-specific')
    def test_windows_bootstrap_and_acceptance_scripts_parse(self):
        files = guest_seed.payload({**self.config(), 'os': 'windows'})
        parser = self.root / 'parse.ps1'
        parser.write_text('$tokens=$null; $errors=$null; '
                          '[System.Management.Automation.Language.Parser]::ParseFile($args[0], [ref]$tokens, [ref]$errors) | Out-Null; '
                          'if ($errors.Count) { $errors | Out-String | Write-Error; exit 1 }')
        for name in ('bootstrap.ps1', 'verify.ps1'):
            with self.subTest(script=name):
                script = self.root / name
                script.write_bytes(files[name])
                result = subprocess.run(['powershell.exe', '-NoProfile', '-File', str(parser), str(script)],
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_resume_keeps_windows_disk_boot_priority(self):
        config = self.config()
        config['installer_iso'] = config.pop('base_image')
        config['os'] = 'windows'
        command = vm.arguments(config, self.root, True, first_boot=False)
        self.assertIn('order=c', command)
        self.assertNotIn('order=c,once=d', command)

    def test_interrupted_disk_is_preserved(self):
        config = self.config()
        home = self.root / 'state'
        home.mkdir()
        (home / 'disk.qcow2').write_bytes(b'preserve')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            vm.initialize(config, home)
        self.assertEqual((home / 'disk.qcow2').read_bytes(), b'preserve')

    def test_installer_cold_boot_budget_never_retries_crashes(self):
        for exit_code, launches in [(0, 3), (1, 1)]:
            with self.subTest(exit_code=exit_code):
                config = {**self.config(), 'os': 'windows', 'install_reboots': 2}
                home = self.root / f'cold-{exit_code}'
                home.mkdir()
                (home / 'disk.qcow2').write_bytes(b'retain-disk')
                (home / 'installation.json').write_text(json.dumps({'os': 'windows', 'media_sha256': config['media_sha256']}))

                class Child:
                    pid = 12345
                    returncode = exit_code
                    def __init__(self): self.stdin = io.BytesIO()
                    def poll(self): return self.returncode
                    def wait(self, timeout): return self.returncode

                with patch.object(vm.subprocess, 'Popen', side_effect=lambda *a, **kw: Child()) as launch, \
                     patch.object(vm, 'identity', return_value='fixture-identity'):
                    with self.assertRaisesRegex(RuntimeError, 'exited'):
                        vm.supervise(config, home, False)
                self.assertEqual(launch.call_count, launches)
                for call in launch.call_args_list:
                    self.assertIn('-no-reboot', call.args[0])
                    self.assertNotIn('order=c,once=d', call.args[0])
                self.assertEqual((home / 'disk.qcow2').read_bytes(), b'retain-disk')
                self.assertFalse((home / 'running.json').exists())

    def test_second_session_cannot_remove_existing_session_lock(self):
        config = self.config()
        home = self.root / 'state'
        lease = home / 'session.lock'
        lease.mkdir(parents=True)
        (lease / 'owner.json').write_text('preserve')
        with self.assertRaises(FileExistsError):
            vm.supervise(config, home, False)
        self.assertEqual((lease / 'owner.json').read_text(), 'preserve')

    def test_paused_machine_is_not_published_ready_and_can_be_stopped(self):
        config = self.config(graphical=True, qmp_port=23411)
        home = self.root / 'paused'; home.mkdir()
        (home / 'disk.qcow2').write_bytes(b'preserve')
        (home / 'installation.json').write_text(json.dumps({'os': config['os'], 'media_sha256': config['media_sha256']}))
        child = type('Child', (), {'pid': 12345, 'returncode': None,
            'stdin': io.BytesIO(), 'poll': lambda s: s.returncode, 'wait': lambda s, timeout: s.returncode})()

        class Client:
            def __init__(self, port): pass
            def close(self): pass
            def execute(self, command):
                record = vm.read_record(home)
                (home / ('stop-' + record['token'] + '.json')).write_text('{"force":true}')
                return {'running': False, 'status': 'paused'}

        with patch.object(vm.subprocess, 'Popen', return_value=child), \
             patch.object(vm, 'identity', return_value='fixture'), \
             patch.object(vm, 'owns_listeners', return_value=True), \
             patch('guest_screen.Qmp', Client), \
             patch.object(vm, 'terminate', side_effect=lambda r: setattr(child, 'returncode', 0)), \
             patch.object(vm, 'acceptance', side_effect=AssertionError('Paused guest was accepted')), \
             patch.object(vm, 'write_record', wraps=vm.write_record) as write:
            vm.supervise(config, home, False)
        phases = [call.args[1].get('phase') for call in write.call_args_list]
        self.assertIn('paused', phases)
        self.assertNotIn('ready', phases)
        self.assertFalse((home / 'session.lock').exists())

    def test_multiple_work_vms_are_supervised_independently(self):
        # Real native QEMU processes exercise PID identity, per-guest leases and
        # concurrent stop delivery without downloading or booting an OS image.
        accelerator = os.environ.get('QEMU_TEST_ACCEL')
        if not accelerator:
            self.skipTest('Native QEMU smoke test requires explicit QEMU_TEST_ACCEL opt-in')
        import shutil
        qemu = shutil.which('qemu-system-x86_64')
        image = shutil.which('qemu-img')
        if not qemu or not image:
            self.skipTest('Native QEMU smoke test requires qemu-system-x86_64 and qemu-img')
        sessions = []
        for index in range(2):
            config = self.config(name=f'work{index}', state_dir=f'state{index}', qemu=qemu,
                                 acceptance=[sys.executable, '-c', 'raise SystemExit(0)'],
                                 qemu_args=['-S', '-accel', accelerator], memory=512)
            home = Path(config['state_dir'])
            home.mkdir()
            subprocess.run([image, 'create', '-f', 'qcow2', str(home / 'disk.qcow2'), '64M'], check=True, stdout=subprocess.DEVNULL)
            (home / 'installation.json').write_text(json.dumps({'os': config['os'], 'media_sha256': config['media_sha256']}))
            (home / 'installed.json').write_text('{}')
            profile = self.root / f'work{index}.json'
            config['ssh_port'] = 32230 + index
            profile.write_text(json.dumps(config))
            log = open(home / 'supervisor.log', 'wb')
            self.addCleanup(log.close)
            process = subprocess.Popen([sys.executable, str(SCRIPTS / 'guest-vm.py'), 'run', str(profile)], stdout=log, stderr=log)
            sessions.append((process, home, profile))
            self.addCleanup(self.cleanup_session, process, home)
        for process, home, _ in sessions:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                record = vm.read_record(home)
                if record and record['phase'] == 'ready':
                    break
                self.assertIsNone(process.poll(), (home / 'supervisor.log').read_text())
                time.sleep(.1)
            else:
                self.fail('Concurrent guest did not become ready')
        first, home, profile = sessions[0]
        subprocess.run([sys.executable, str(SCRIPTS / 'guest-vm.py'), 'stop', str(profile), '--force'], check=True, stdout=subprocess.DEVNULL)
        self.assertEqual(first.wait(timeout=20), 0)
        self.assertFalse((home / 'session.lock').exists())
        self.assertIsNone(sessions[1][0].poll(), 'Stopping one VM stopped another')
        self.assertTrue(vm.alive(vm.read_record(sessions[1][1])))

    @staticmethod
    def cleanup_session(process, home):
        if process.poll() is None:
            record = vm.read_record(home)
            if record:
                (home / ('stop-' + record['token'] + '.json')).write_text('{"force":true}')
                process.wait(timeout=20)
            else:
                process.terminate()
                process.wait(timeout=10)


if __name__ == '__main__':
    unittest.main()
