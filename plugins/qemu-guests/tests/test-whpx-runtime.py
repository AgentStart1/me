"""Managed runtime integrity and explicit WHPX configuration contracts."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import whpx_runtime as runtime
import guest_config


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)

    def stage(self):
        files = {}
        for name in ('bin/qemu-system-x86_64.exe', 'share/qemu/bios-256k.bin', 'share/qemu/vgabios-stdvga.bin'):
            path = self.home / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'fixture')
            files[name] = runtime.digest(path)
        (self.home / 'runtime.json').write_text(json.dumps({
            'recipe': runtime.recipe(), 'sourceSha256': runtime.SOURCE_SHA, 'files': files}))

    def test_corrupt_cached_executable_is_rejected_before_execution(self):
        self.stage()
        (self.home / 'bin/qemu-system-x86_64.exe').write_bytes(b'corrupt')
        with patch.object(runtime.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'verification failed'):
                runtime.verify(self.home)
            run.assert_not_called()

    def test_tcg_capable_binary_is_rejected(self):
        self.stage()
        result = subprocess.CompletedProcess([], 0, 'Accelerators supported in QEMU binary:\nwhpx\ntcg\n')
        with patch.object(runtime.subprocess, 'run', return_value=result):
            with self.assertRaisesRegex(ValueError, 'WHPX only'):
                runtime.verify(self.home)

    @unittest.skipUnless(os.name == 'nt', 'Windows runtime cache')
    def test_valid_cache_does_not_rebuild(self):
        stage = runtime.location(self.home) / 'runtime'
        stage.mkdir(parents=True)
        with patch.object(runtime, 'verify', return_value=stage / 'bin/qemu-system-x86_64.exe'), \
                patch.object(runtime.ctypes, 'WinDLL'), \
                patch.object(runtime, 'msys_root') as msys:
            executable = runtime.build(self.home)
        self.assertEqual(executable.parent.parent, stage)
        msys.assert_not_called()

    def test_runtime_preparation_never_falls_back_when_build_fails(self):
        config = {'qemu_runtime': 'whpx-reset', 'qemu_args': ['-accel', 'whpx', '-cpu', 'Westmere,-vmx,-svm']}
        with patch.object(runtime, 'build', side_effect=RuntimeError('build failed')):
            with self.assertRaisesRegex(RuntimeError, 'build failed'):
                runtime.prepare(config)

    @unittest.skipUnless(os.name == 'nt', 'Windows build preflight')
    def test_source_checksum_failure_precedes_compiler_execution(self):
        archive = self.home / 'source.tar.xz'
        archive.write_bytes(b'invalid source')
        with patch.object(runtime.ctypes, 'WinDLL'), patch.object(runtime, 'msys_root', return_value=self.home), \
                patch.object(runtime.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                runtime.build(self.home / 'cache', archive=archive)
        run.assert_not_called()
        self.assertFalse((runtime.location(self.home / 'cache') / 'runtime').exists())
        self.assertTrue(archive.exists())

    def test_runtime_rejects_system_executable_override(self):
        with self.assertRaisesRegex(ValueError, 'owns the executable'):
            runtime.prepare({'qemu_runtime': 'whpx-reset', 'qemu': 'qemu-system-x86_64.exe'})

    def test_plan_resolves_managed_paths_without_building(self):
        config = {'qemu_runtime': 'whpx-reset', 'qemu_args': ['-accel', 'whpx', '-cpu', 'Westmere,-vmx,-svm']}
        with patch.object(runtime, 'build') as build:
            planned = runtime.prepare(config, build_runtime=False)
        build.assert_not_called()
        self.assertTrue(planned['qemu'].endswith('qemu-system-x86_64.exe'))
        self.assertEqual(planned['qemu_args'][-2], '-L')

    def test_windows_sample_defaults_to_four_core_warm_reset(self):
        path = Path(__file__).resolve().parents[1] / 'profiles/windows.json'
        config = guest_config.load(path)
        self.assertEqual((config['cpus'], config['qemu_runtime'], config['install_reboots']), (4, 'whpx-reset', 0))
        self.assertEqual(config['qemu_args'], ['-accel', 'whpx', '-cpu', 'Westmere,-vmx,-svm'])


if __name__ == '__main__':
    unittest.main()
