"""Managed runtime integrity and explicit WHPX configuration contracts."""
import json
import importlib.util
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

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

    def test_staged_file_verification_does_not_execute_before_publication(self):
        self.stage()
        with patch.object(runtime.subprocess, 'run') as run:
            runtime.verify_files(self.home)
            run.assert_not_called()
            run.return_value = subprocess.CompletedProcess([], 0, 'Accelerators supported in QEMU binary:\nwhpx\n')
            runtime.verify(self.home)
            run.assert_called_once()

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


class CetCpuidTests(unittest.TestCase):
    def test_native_cet_matrix_preserves_model_and_host_bounds(self):
        compiler = shutil.which('gcc') or shutil.which('clang') or shutil.which('cc')
        fallback = Path.home() / 'msys2/ucrt64/bin/gcc.exe'
        compiler = compiler or (str(fallback) if os.name == 'nt' and fallback.exists() else None)
        if not compiler:
            self.skipTest('Native C compiler is unavailable')
        patch = runtime.PATCHES[1].read_text()
        body = patch.split('+++ b/target/i386/whpx/whpx-cpuid.h\n', 1)[1]
        header = ''.join(line[1:] + '\n' for line in body.splitlines() if line.startswith('+'))
        program = r'''#include <assert.h>
#include "whpx-cpuid.h"
int main(void) {
    const uint32_t masks[] = {1u << 7, 1u << 20};
    for (unsigned k = 0; k < 2; k++) {
        uint32_t mask = masks[k], unrelated = 0x5aa50a55u & ~mask;
        for (unsigned model = 0; model < 2; model++)
        for (unsigned host = 0; host < 2; host++)
        for (unsigned xsave = 0; xsave < 2; xsave++)
        for (unsigned xsaves = 0; xsaves < 2; xsaves++) {
            uint32_t value = whpx_filter_cet_cpuid(
                unrelated | (model ? mask : 0), host ? mask : 0,
                mask, xsave, xsaves);
            assert((value & ~mask) == unrelated);
            if (!model || !host || !xsave || !xsaves) assert(!(value & mask));
            if (model && host && xsave && xsaves) assert(value & mask);
        }
    }
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'whpx-cpuid.h').write_text(header)
            source = root / 'matrix.c'; source.write_text(program)
            executable = root / ('matrix.exe' if os.name == 'nt' else 'matrix')
            compiled = subprocess.run([compiler, '-std=c11', '-Wall', '-Werror', str(source), '-o', str(executable)],
                                      capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            subprocess.run([str(executable)], check=True, capture_output=True, timeout=10)

    def test_cet_patch_changes_runtime_cache_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reset = root / 'reset.patch'; reset.write_bytes(b'reset')
            cet = root / 'cet.patch'; cet.write_bytes(b'first CET recipe')
            with patch.object(runtime, 'PATCHES', (reset, cet)):
                before = runtime.location(root)
                cet.write_bytes(b'changed CET recipe')
                after = runtime.location(root)
            self.assertNotEqual(before, after)


class RebootAcceptanceTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).with_name('validate-whpx-reboots.py')
        spec = importlib.util.spec_from_file_location('reboot_acceptance', path)
        self.probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.probe)

    def test_appium_startup_waits_after_ssh_recovers(self):
        ssh = Mock(side_effect=[subprocess.TimeoutExpired('fixture', 1),
                               subprocess.CompletedProcess([], 1), subprocess.CompletedProcess([], 0)])
        unchanged = Mock()
        with patch.object(self.probe.time, 'monotonic', return_value=0), patch.object(self.probe.time, 'sleep'):
            self.probe.wait_appium(ssh, unchanged, 30)
        self.assertEqual(ssh.call_count, 3)
        self.assertEqual(unchanged.call_count, 6)
        self.assertTrue(all(call.args[1] <= 15 for call in ssh.call_args_list))

    def test_appium_readiness_does_not_extend_cycle_deadline(self):
        ssh = Mock(return_value=subprocess.CompletedProcess([], 1))
        with patch.object(self.probe.time, 'monotonic', side_effect=[9, 10, 10]), patch.object(self.probe.time, 'sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError, 'Appium acceptance timed out'):
                self.probe.wait_appium(ssh, Mock(), 10)
        ssh.assert_called_once()
        self.assertEqual(ssh.call_args.args[1], 1)
        sleep.assert_not_called()

    def test_appium_success_cannot_hide_replaced_qemu(self):
        ssh = Mock(return_value=subprocess.CompletedProcess([], 0))
        unchanged = Mock(side_effect=[None, RuntimeError('QEMU replaced')])
        with patch.object(self.probe.time, 'monotonic', return_value=0):
            with self.assertRaisesRegex(RuntimeError, 'QEMU replaced'):
                self.probe.wait_appium(ssh, unchanged, 30)


if __name__ == '__main__':
    unittest.main()
