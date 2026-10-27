"""GPU cache integrity, profile isolation and readiness failure contracts; no VM starts."""
import importlib.util
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import guest_config
import guest_gpu
import guest_registry
import guest_screen
import virgl_runtime as runtime
from whpx_runtime import digest

spec = importlib.util.spec_from_file_location('virgl_guest_vm', ROOT / 'scripts/guest-vm.py')
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)


class VirglTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.config = {'os': 'ubuntu', 'graphical': True, 'qemu_runtime': 'virgl-whpx',
                       'qemu_args': runtime.CPU_ARGS, 'hardware_args': []}

    def stage(self):
        files = {}
        for relative in ['bin/qemu-system-x86_64.exe', 'bin/libvirglrenderer-1.dll',
                         'recipe/qemu-gl-snapshot.patch',
                         'bin/SDL2.dll', 'bin/libepoxy-0.dll', 'share/qemu/vgabios-virtio.bin',
                         'share/qemu/bios-256k.bin', 'share/qemu/vgabios-stdvga.bin']:
            path = self.home / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'fixture')
            files[relative] = digest(path)
        snapshot = runtime.Snapshot.capture()
        (self.home / 'runtime.json').write_text(json.dumps({'recipe': snapshot.recipe(),
                        'sourceSha256': snapshot.source_sha, 'files': files}))

    def test_modified_renderer_is_rejected_before_executable_probe(self):
        self.stage()
        (self.home / 'bin/libvirglrenderer-1.dll').write_bytes(b'changed')
        with patch.object(runtime.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'verification failed'):
                runtime.verify(self.home)
        run.assert_not_called()

    def test_recipe_captures_build_inputs_and_changes_cache_for_new_template(self):
        plugin = self.home / 'plugin'
        for name in ['patches', 'templates']:
            shutil.copytree(ROOT / name, plugin / name)
        with patch.object(runtime, 'ROOT', plugin):
            first = runtime.Snapshot.capture()
            target = plugin / 'templates/build-virgl-whpx.sh'
            target.write_bytes(target.read_bytes() + b'\n# changed recipe\n')
            second = runtime.Snapshot.capture()
        self.assertNotEqual(first.recipe(), second.recipe())
        self.assertNotEqual(runtime.location(self.home, first), runtime.location(self.home, second))
        self.assertNotIn(b'changed recipe', first.inputs[0].content)

    def test_snapshot_patch_changes_the_runtime_cache_identity(self):
        plugin = self.home / 'plugin'
        for name in ['patches', 'templates']:
            shutil.copytree(ROOT / name, plugin / name)
        with patch.object(runtime, 'ROOT', plugin):
            before = runtime.Snapshot.capture()
            target = plugin / 'patches/qemu-11.1.2-sdl-gl-snapshot.patch'
            target.write_bytes(target.read_bytes() + b'\n# changed snapshot patch\n')
            after = runtime.Snapshot.capture()
        self.assertNotEqual(before.recipe(), after.recipe())
        self.assertIn('qemu-gl-snapshot.patch', [item.name for item in before.inputs])

    @unittest.skipUnless(os.name == 'nt', 'Windows build preflight')
    def test_bad_archive_cannot_start_a_compiler_or_publish_runtime(self):
        archive = self.home / 'qemu.tar.xz'
        archive.write_bytes(b'corrupt archive')
        cache = self.home / 'cache'
        with patch.object(runtime.ctypes, 'WinDLL'), patch.object(runtime, 'msys_root', return_value=self.home), \
                patch.object(runtime.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'source checksum mismatch'):
                runtime.build(cache=cache, qemu_archive=archive)
        run.assert_not_called()
        self.assertFalse((runtime.location(cache) / 'runtime').exists())
        self.assertFalse((runtime.location(cache) / 'build.lock').exists())
        self.assertTrue(archive.exists())

    def test_runtime_rejects_missing_hidden_display_support(self):
        self.stage()
        probes = [subprocess.CompletedProcess([], 0, 'Accelerators supported in QEMU binary:\nwhpx\n'),
                  subprocess.CompletedProcess([], 0, 'name "virtio-vga-gl", bus PCI'),
                  subprocess.CompletedProcess([], 1, '', 'Parameter hidden is unexpected')]
        with patch.object(runtime.subprocess, 'run', side_effect=probes):
            with self.assertRaisesRegex(ValueError, 'hidden SDL'):
                runtime.verify(self.home)

    def test_plan_selects_gpu_arguments_without_building(self):
        with patch.object(runtime, 'build') as build:
            result = runtime.prepare(self.config, False)
        build.assert_not_called()
        self.assertIn('virtio-vga-gl', result['qemu_args'])
        self.assertIn('sdl,gl=on,hidden=on', result['qemu_args'])
        self.assertEqual(self.config['qemu_args'], runtime.CPU_ARGS)

    def test_operator_cache_selection_applies_to_profile_planning(self):
        selected = self.home / 'operator-cache'
        with patch.dict(os.environ, {'QEMU_VIRGL_CACHE': str(selected)}):
            planned = runtime.prepare(self.config, False)
            self.assertTrue(Path(planned['qemu']).is_relative_to(selected))
            self.assertTrue(runtime.location(self.home / 'explicit').is_relative_to(self.home / 'explicit'))

    def test_foreign_guest_executable_and_hardware_overrides_are_rejected(self):
        for override in [{'os': 'windows'}, {'graphical': False}, {'qemu': 'custom.exe'},
                         {'hardware_args': ['-vga', 'std']}, {'qemu_args': ['-accel', 'tcg']}]:
            with self.subTest(override=override), self.assertRaises(ValueError):
                runtime.prepare({**self.config, **override}, False)

    def test_build_failure_cannot_fall_back_to_system_qemu(self):
        with patch.object(runtime, 'build', side_effect=RuntimeError('build failed')):
            with self.assertRaisesRegex(RuntimeError, 'build failed'):
                runtime.prepare(self.config)

    def test_software_renderer_cannot_publish_gpu_readiness(self):
        for name in ['llvmpipe', 'virgl (llvmpipe)', 'virgl (Microsoft Basic Render Driver)', 'virgl (WARP)']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                guest_gpu.renderer('Accelerated: yes\nOpenGL renderer string: ' + name)
        self.assertEqual(guest_gpu.renderer('Accelerated: yes\nOpenGL renderer string: virgl (GPU)'), 'virgl (GPU)')

    def test_receipts_from_prior_boot_or_reused_session_pid_are_rejected(self):
        record = {'boot_id': 'boot-a', 'session_pid': 123, 'session_start': '10'}
        with self.assertRaisesRegex(ValueError, 'stale'):
            guest_gpu.verify_session(record, 'boot-b')
        with patch.object(guest_gpu, 'process_start', return_value='11'):
            with self.assertRaisesRegex(ValueError, 'stale'):
                guest_gpu.verify_session(record, 'boot-a')

    def test_initial_boot_requires_cloud_init_but_cold_boot_keeps_desktop_checks(self):
        config = {**self.config, 'acceptance': [], 'ssh_port': 2230,
                  'access_key': 'fixture', 'ssh_user': 'tester'}
        self.assertIn('cloud-init status', vm.acceptance(config, self.home)[-1])
        (self.home / 'installed.json').write_text('{"os":"ubuntu"}')
        command = vm.acceptance(config, self.home)[-1]
        self.assertNotIn('cloud-init', command)
        self.assertIn('verify.py', command)

    def test_gpu_profile_cannot_adopt_an_existing_software_installation(self):
        base = {'os': 'ubuntu', 'media_sha256': '0' * 64}
        self.assertNotEqual(vm.installation_record(base), vm.installation_record({**base, **self.config}))
        self.assertEqual(vm.installation_record(base), base)

    def test_gpu_screen_does_not_connect_to_qmp_without_a_surface(self):
        item = {'id': 'a' * 24, 'graphical': True, 'qmp_capture': False}
        with patch.object(guest_screen, 'entries', return_value=[item]), patch.object(guest_screen, 'Qmp') as qmp:
            with self.assertRaisesRegex(ValueError, 'native Appium'):
                guest_screen.capture(item['id'])
        qmp.assert_not_called()

    def test_gpu_profile_validation_requires_ubuntu_graphics(self):
        profile = json.loads((ROOT / 'profiles/ubuntu-virgl-whpx.json').read_text())
        path = self.home / 'guest.json'
        for override in [{'graphical': False}, {'os': 'windows'}]:
            path.write_text(json.dumps({**profile, **override}))
            with self.subTest(override=override), self.assertRaisesRegex(ValueError, 'graphical Ubuntu'):
                guest_config.load(path)

    def test_gpu_install_requires_project_requirements_before_checking_media(self):
        with self.assertRaisesRegex(ValueError, '--requirements'):
            guest_config.verify_inputs(self.config)

    def test_gpu_panel_advertises_the_managed_snapshot_backend(self):
        config = {**self.config, 'name': 'gpu-fixture', 'memory': 4096, 'cpus': 4,
                  'ssh_port': 2230, 'qmp_port': 2231}
        with patch.object(guest_registry, 'directory', return_value=self.home / 'registry'):
            guest_registry.register(config, self.home)
            with patch.object(guest_registry, 'state', return_value=('ready', {'pid': 123})):
                item = guest_registry.snapshot()['items'][0]
        self.assertEqual(item['state'], 'ready')
        self.assertTrue(item['screenAvailable'])


if __name__ == '__main__':
    unittest.main()
