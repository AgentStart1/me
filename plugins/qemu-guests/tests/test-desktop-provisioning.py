"""Portable dependency declarations and unattended desktop seed contracts."""
import hashlib
import getpass
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from guest_desktop import validate
from guest_seed import payload, prepare_seed
from test_requirements import apply, verify_runtime, verify_runtime_target


class DesktopProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.requirements = self.root / 'requirements.json'
        self.data = {'version': 1, 'desktop': {'width': 1920, 'height': 1080}, 'platforms': {
            'Linux': {'java': 21, 'packages': ['openjdk-21-jre'], 'appium': {
                'version': '3.2.2', 'drivers': {'linux': '0.1.0'}, 'plugins': {}}},
            'Windows': {'java': 21, 'appium': {'version': '3.2.2', 'drivers': {'desktopdriver': '2.8.0'}, 'plugins': {'desktop': '0.1.0'}}}}}
        self.requirements.write_text(json.dumps(self.data))
        key = self.root / 'key'; Path(str(key) + '.pub').write_text('ssh-ed25519 AAAA fixture')
        runtime = self.root / 'runtime.zip'
        with zipfile.ZipFile(runtime, 'w') as archive:
            archive.writestr('runtime.json', json.dumps({'appium': '3.2.2', 'platform': 'linux', 'arch': 'x64',
                'extensions': {'drivers': {'linux': '0.1.0'}, 'plugins': {}}}))
        self.config = {'os': 'ubuntu', 'name': 'fixture', 'graphical': True, 'ssh_user': 'tester',
                       'access_key': str(key), 'appium': {'runtime_archive': str(runtime)}}

    def test_requirements_select_platform_without_connection_or_provider_fields(self):
        result = apply(self.config, self.requirements)
        self.assertEqual(result['desktop']['packages'], ['openjdk-21-jre'])
        self.assertNotIn('desktop', self.config)
        self.assertEqual(result['runtime_requirements']['sha256'], hashlib.sha256(self.requirements.read_bytes()).hexdigest())

    def test_provider_fields_are_rejected_in_project_requirements(self):
        self.data['ssh_port'] = 2222; self.requirements.write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError, 'Runtime requirements'):
            apply(self.config, self.requirements)

    def test_runtime_inventory_must_match_project_extensions(self):
        config = apply(self.config, self.requirements)
        verify_runtime(self.config['appium']['runtime_archive'], config['runtime_requirements'], 'ubuntu')
        config['runtime_requirements']['runtime']['appium']['drivers']['linux'] = '0.2.0'
        with self.assertRaisesRegex(ValueError, 'extension/version'):
            verify_runtime(self.config['appium']['runtime_archive'], config['runtime_requirements'], 'ubuntu')

    def test_missing_prebuilt_classpath_dependency_fails_before_provisioning(self):
        config = apply(self.config, self.requirements)
        config['runtime_requirements']['runtime']['classpath'] = ['example:native:1.0']
        with self.assertRaisesRegex(ValueError, 'native classpath'):
            verify_runtime(self.config['appium']['runtime_archive'], config['runtime_requirements'], 'ubuntu')

    def test_linux_seed_initializes_isolated_session_and_project_runtime_packages(self):
        config = apply(self.config, self.requirements)
        prepare_seed(config, self.root / 'seed')
        cloud = json.loads((self.root / 'seed/user-data').read_text().split('\n', 1)[1])
        self.assertIn('openjdk-21-jre', cloud['packages'])
        self.assertIn('gnome-keyring', cloud['packages'])
        self.assertIn('python3-pyatspi', cloud['packages'])
        entries = {p['path']: p for p in cloud['write_files']}
        self.assertIn('autologin-user=tester', entries['/etc/lightdm/lightdm.conf.d/60-test-autologin.conf']['content'])
        self.assertIn('autologin-session=xfce', entries['/etc/lightdm/lightdm.conf.d/60-test-autologin.conf']['content'])
        files = payload(config)
        script = files['desktop-session.sh'].decode()
        self.assertIn('1920x1080x24', script)
        self.assertIn('gnome-keyring-daemon --unlock', script)
        self.assertIn('Xvfb :99', script)
        self.assertNotIn('-displayfd', script)
        self.assertIn("'xfce4-session'", files['verify.py'].decode())
        self.assertNotIn('gradlew', script)
        self.assertNotIn('npm install', script)

    def test_windows_only_loads_host_compiled_display_helper(self):
        config = apply({**self.config, 'os': 'windows'}, self.requirements)
        files = payload(config)
        script = files['desktop-setup.ps1'].decode()
        self.assertIn('Add-Type -Path', script)
        self.assertNotIn('Add-Type -TypeDefinition', script)
        self.assertNotIn('desktop-helper.cs', files)
        bootstrap = files['bootstrap.ps1'].decode()
        self.assertIn('Restart-Computer', bootstrap)
        self.assertIn('AppliedDPI', bootstrap)

    def test_gpu_seed_uses_console_without_changing_project_requirements(self):
        config = apply({**self.config, 'qemu_runtime': 'virgl-whpx'}, self.requirements)
        before = self.requirements.read_bytes()
        prepare_seed(config, self.root / 'gpu-seed')
        cloud = json.loads((self.root / 'gpu-seed/user-data').read_text().split('\n', 1)[1])
        self.assertIn('mesa-utils', cloud['packages'])
        self.assertEqual(cloud['runcmd'][-1], ['systemctl', 'restart', 'lightdm'])
        files = payload(config)
        script = files['desktop-session.sh'].decode()
        self.assertNotIn('Xvfb', script)
        self.assertNotIn('openbox --', script)
        self.assertNotIn('unset XAUTHORITY', script)
        self.assertIn('verify-gpu.py', script)
        self.assertIn('gnome-keyring-daemon --unlock', script)
        self.assertIn('dbus-run-session', files['desktop-autostart.desktop'].decode())
        self.assertIn('systemctl disable --now', files['bootstrap.sh'].decode())
        self.assertEqual(self.requirements.read_bytes(), before)

    @unittest.skipUnless(os.name == 'posix', 'POSIX bootstrap permissions')
    def test_gpu_bootstrap_makes_verifier_readable_after_private_seed_extraction(self):
        config = apply({**self.config, 'ssh_user': getpass.getuser(),
                        'qemu_runtime': 'virgl-whpx'}, self.requirements)
        runtime = Path(config['appium']['runtime_archive'])
        with zipfile.ZipFile(runtime, 'a') as archive:
            archive.writestr('node', '#!/bin/sh\nexit 0\n')
        destination = self.root / 'guest'
        destination.mkdir()
        for name, content in payload(config).items():
            path = destination / name
            path.write_bytes(content)
            path.chmod(0o600)
        system = self.root / 'system'
        system.mkdir()
        home = self.root / 'home'
        home.mkdir()
        tools = self.root / 'tools'
        tools.mkdir()
        for name, body in {'getent': 'printf "%s\\n" "$TEST_PASSWD_ENTRY"',
                           'systemctl': 'printf "%s\\n" "$*" >> "$TEST_SYSTEMCTL_LOG"'}.items():
            path = tools / name
            path.write_text('#!/bin/sh\n' + body + '\n')
            path.chmod(0o755)
        script = destination / 'bootstrap.sh'
        script.write_text(script.read_text().replace('/opt/qemu-guests', str(destination))
                          .replace('/etc/systemd/system', str(system)))
        log = self.root / 'systemctl.log'
        env = {**os.environ, 'PATH': str(tools) + os.pathsep + os.environ['PATH'],
               'TEST_PASSWD_ENTRY': f'{getpass.getuser()}:x:1000:1000:fixture:{home}:/bin/sh',
               'TEST_SYSTEMCTL_LOG': str(log)}
        subprocess.run(['/bin/sh', str(script)], env=env, check=True, capture_output=True)
        self.assertTrue((destination / 'verify-gpu.py').stat().st_mode & 0o004)
        self.assertTrue((home / '.config/autostart/qemu-guests-appium.desktop').exists())
        self.assertIn('disable --now qemu-guests-appium.service', log.read_text())
        self.assertNotIn('enable --now', log.read_text())

    def test_invalid_geometry_and_package_injection_are_rejected(self):
        for value in [{'width': True}, {'height': 0}, {'packages': ['curl; reboot']}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate(value, 'ubuntu', True)

    def test_run_rejects_uninitialized_requirements_before_touching_vm_state(self):
        scripts = Path(__file__).resolve().parents[1] / 'scripts'
        spec = importlib.util.spec_from_file_location('desktop_guest_vm', scripts / 'guest-vm.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        profile = self.root / 'guest.json'
        state = self.root / 'state'
        profile.write_text(json.dumps({**self.config, 'state_dir': str(state), 'ssh_port': 2240, 'qmp_port': 2241,
            'base_image': 'base.img', 'appium': {**self.config['appium'], 'host_port': 24730, 'sha256': '0' * 64}}))
        with self.assertRaisesRegex(ValueError, 'not initialized'):
            module.main(['run', str(profile), '--requirements', str(self.requirements)])
        self.assertFalse(state.exists())

    def test_project_requirements_reject_boolean_schema_version(self):
        self.data['version'] = True; self.requirements.write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError, 'version:1'):
            apply(self.config, self.requirements)

    def runtime_fixture(self, platform, arch='x64'):
        path = self.root / 'target-runtime.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('runtime.json', json.dumps({'platform': platform, 'arch': arch,
                'appium': '3.2.2', 'extensions': {'drivers': {'linux': '0.1.0'}, 'plugins': {}}}))
        return path

    def test_runtime_target_accepts_supported_os_and_x64_pairs(self):
        for system, platform in [('ubuntu', 'linux'), ('windows', 'win32'), ('macos', 'darwin')]:
            with self.subTest(system=system):
                verify_runtime_target(self.runtime_fixture(platform), system)

    def test_runtime_inventory_rejects_foreign_os_before_extension_checks(self):
        for system, platform in [('windows', 'linux'), ('ubuntu', 'win32')]:
            with self.subTest(system=system):
                config = apply({**self.config, 'os': system}, self.requirements)
                with self.assertRaisesRegex(ValueError, 'runtime target'):
                    verify_runtime(self.runtime_fixture(platform), config['runtime_requirements'], system)

    def test_runtime_target_rejects_wrong_or_missing_architecture(self):
        for arch in ['arm64', 'ia32', None]:
            with self.subTest(arch=arch), self.assertRaisesRegex(ValueError, 'linux/x64'):
                verify_runtime_target(self.runtime_fixture('linux', arch), 'ubuntu')

    def test_wrong_runtime_cannot_create_a_disk_with_or_without_requirements(self):
        scripts = Path(__file__).resolve().parents[1] / 'scripts'
        spec = importlib.util.spec_from_file_location('target_guest_vm', scripts / 'guest-vm.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        Path(self.config['access_key']).write_bytes(b'private fixture')
        runtime = self.runtime_fixture('win32')
        config = {**self.config, 'appium': {'runtime_archive': str(runtime),
                  'sha256': hashlib.sha256(runtime.read_bytes()).hexdigest()}}
        for requirements in [False, True]:
            with self.subTest(requirements=requirements):
                selected = apply(config, self.requirements) if requirements else config
                home = self.root / 'untouched-state'
                with patch.object(module.subprocess, 'run') as command:
                    with self.assertRaisesRegex(ValueError, 'linux/x64'):
                        module.initialize(selected, home)
                command.assert_not_called()
                self.assertFalse(home.exists())

    def test_preparation_rejects_wrong_target_before_host_hooks(self):
        scripts = Path(__file__).resolve().parents[1] / 'scripts'
        spec = importlib.util.spec_from_file_location('target_runtime_prepare', scripts / 'prepare-appium-runtime.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        output = self.root / 'not-created.zip'
        with patch.object(module.shutil, 'which', return_value='node'), \
                patch('project_setup_hooks.prepare_host') as hooks:
            with self.assertRaisesRegex(ValueError, 'win32/x64'):
                module.prepare(self.runtime_fixture('linux'), output, [],
                               requirements=self.requirements, platform='windows')
        hooks.assert_not_called()
        self.assertFalse(output.exists())

    def test_existing_vm_run_does_not_revalidate_or_rewrite_legacy_runtime(self):
        scripts = Path(__file__).resolve().parents[1] / 'scripts'
        spec = importlib.util.spec_from_file_location('legacy_guest_vm', scripts / 'guest-vm.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        runtime = self.runtime_fixture('linux', None)
        state = self.root / 'existing-state'; state.mkdir()
        disk = state / 'disk.qcow2'; disk.write_bytes(b'existing disk fixture')
        recorded = state / 'runtime-requirements.json'
        recorded.write_text(json.dumps(apply(self.config, self.requirements)['runtime_requirements']))
        before = recorded.read_bytes(), disk.read_bytes(), runtime.read_bytes()
        profile = self.root / 'existing.json'
        profile.write_text(json.dumps({**self.config, 'state_dir': str(state), 'ssh_port': 2240, 'qmp_port': 2241,
            'base_image': 'base.img', 'appium': {'runtime_archive': str(runtime), 'host_port': 24730, 'sha256': '0' * 64}}))
        with patch('whpx_runtime.prepare', side_effect=lambda config: config), \
                patch.object(module, 'supervise') as supervise, \
                patch.object(module.signal, 'signal'), \
                patch.object(module, 'verify_inputs') as validate_install:
            module.main(['run', str(profile), '--requirements', str(self.requirements)])
        self.assertFalse(supervise.call_args.args[2])
        validate_install.assert_not_called()
        self.assertEqual((recorded.read_bytes(), disk.read_bytes(), runtime.read_bytes()), before)


if __name__ == '__main__':
    unittest.main()
