"""Portable dependency packaging, runtime selection and EFI preservation contracts."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import macos_gpu_boot as boot
import reims_runtime as runtime
import reims_sources as sources
spec = importlib.util.spec_from_file_location('guest_vm', ROOT / 'scripts/guest-vm.py')
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)


class RuntimeTests(unittest.TestCase):
    def test_operator_cache_override_is_shared_by_build_and_plan(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(runtime.os.environ, {'QEMU_REIMS_CACHE': directory}):
            self.assertEqual(runtime.location().parent, Path(directory))
            self.assertEqual(runtime.location(cache=Path(directory) / 'explicit').parent,
                             Path(directory) / 'explicit')

    def test_repository_patches_and_guest_artifact_match_their_locks(self):
        snapshot = sources.Snapshot.capture()
        self.assertEqual(len(snapshot.patches), 3)
        self.assertEqual(boot.verified_driver('24H32').architecture, 'x86_64')

    def test_patch_tampering_is_rejected_before_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'patches/reims-windows', root / 'patches/reims-windows')
            shutil.copytree(ROOT / 'templates', root / 'templates')
            (root / 'patches/reims-windows/qemu.patch').write_bytes(b'changed')
            with patch.object(sources, 'ROOT', root), self.assertRaisesRegex(ValueError, 'checksum'):
                sources.Snapshot.capture()

    def test_captured_recipe_does_not_reread_changed_inputs(self):
        snapshot = sources.Snapshot.capture()
        before = snapshot.recipe()
        with tempfile.TemporaryDirectory() as directory:
            snapshot.write(Path(directory) / 'inputs')
            (Path(directory) / 'inputs/qemu.patch').write_bytes(b'changed')
        self.assertEqual(snapshot.recipe(), before)

    def test_checkout_applies_patches_to_new_repositories_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream = root / 'upstream'
            upstream.mkdir()

            def git(*args):
                return subprocess.check_output(['git', '-C', str(upstream), *args], stderr=subprocess.DEVNULL)

            git('init', '-q')
            git('config', 'core.autocrlf', 'false')
            (upstream / 'value').write_bytes(b'before\n')
            git('add', 'value')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')
            revision = git('rev-parse', 'HEAD').decode().strip()
            (upstream / 'value').write_bytes(b'after\n')
            diff = git('diff', '--', 'value')
            git('add', 'value')
            expected_tree = git('write-tree').decode().strip()
            git('reset', '--mixed', 'HEAD')
            (upstream / 'value').write_bytes(b'before\n')
            lock = {'sources': {name: {'url': str(upstream), 'revision': revision, 'patch': 'fix.patch',
                                      'patched_tree': expected_tree}
                                for name in ('metal2vulkan', 'reims-vgpu', 'qemu')}}
            snapshot = sources.Snapshot(json.dumps(lock).encode(), (sources.Input('fix.patch', diff),), ())
            work = root / 'work'
            work.mkdir()
            with (root / 'build.log').open('wb') as log:
                trees = sources.checkout(snapshot, work, log)
            self.assertTrue(all((tree / 'value').read_bytes() == b'after\n' for tree in trees.values()))
            self.assertEqual((upstream / 'value').read_bytes(), b'before\n')
            self.assertEqual(git('rev-parse', 'HEAD').decode().strip(), revision)
            with (root / 'build.log').open('ab') as log, self.assertRaisesRegex(ValueError, 'empty'):
                sources.checkout(snapshot, work, log)

    def test_managed_profile_uses_bundled_rom_without_building_during_plan(self):
        config = {'os': 'macos', 'qemu_args': list(runtime.CPU_ARGS),
                  'hardware_args': ['-device', 'apple-gfx-pci,romfile={reims_rom}']}
        with patch.object(runtime, 'build') as build:
            value = runtime.prepare(config, build_runtime=False)
        build.assert_not_called()
        self.assertIn('runtime/share/qemu/ReimsVgpu.rom', value['hardware_args'][1].replace('\\', '/'))
        self.assertEqual(config['hardware_args'][1], 'apple-gfx-pci,romfile={reims_rom}')

    def test_runtime_refuses_unqualified_cpu_or_executable_overrides(self):
        config = {'os': 'macos', 'qemu_args': runtime.CPU_ARGS, 'hardware_args': []}
        for changes in ({'os': 'windows'}, {'qemu': 'other.exe'}, {'qemu_args': ['-accel', 'tcg']}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                runtime.prepare({**config, **changes}, build_runtime=False)

    def test_gpu_environment_is_scoped_to_qualified_runtime(self):
        with patch.dict(vm.os.environ, {'REIMS_VGPU_WINDOW': '1'}):
            self.assertEqual(vm.process_environment({'qemu_runtime': 'reims-whpx'})['REIMS_VGPU_WINDOW'], '0')
            self.assertEqual(vm.os.environ['REIMS_VGPU_WINDOW'], '1')
            self.assertIsNone(vm.process_environment({'qemu_runtime': 'whpx-reset'}))

    def test_unknown_guest_build_is_rejected_without_creating_image(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'output.raw'
            with self.assertRaisesRegex(ValueError, '24H32'):
                boot.prepare(Path(directory) / 'input.raw', output, '25A1')
            self.assertFalse(output.exists())

    def test_existing_receipt_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / 'source.raw', Path(directory) / 'output.raw'
            source.write_bytes(b'original')
            receipt = output.with_suffix('.raw.json')
            receipt.write_bytes(b'previous evidence')
            with self.assertRaisesRegex(ValueError, 'overwritten'):
                boot.prepare(source, output, '24H32')
            self.assertEqual(receipt.read_bytes(), b'previous evidence')
            self.assertFalse(output.exists())

    def test_source_cannot_be_the_receipt_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'output.raw'
            source = output.with_suffix('.raw.json')
            source.write_bytes(b'original image')
            with self.assertRaisesRegex(ValueError, 'overwritten'):
                boot.prepare(source, output, '24H32')
            self.assertEqual(source.read_bytes(), b'original image')
            self.assertFalse(output.exists())

    def test_receipt_created_during_preparation_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / 'source.raw', Path(directory) / 'output.raw'
            source.write_bytes(b'original')
            archive = Path(directory) / 'lilu.zip'
            archive.touch()
            receipt = output.with_suffix('.raw.json')
            def competing_receipt(*args):
                receipt.write_bytes(b'competing evidence')
                return {}
            with patch.object(boot, 'lilu_files', side_effect=competing_receipt):
                with self.assertRaises(FileExistsError):
                    boot.prepare(source, output, '24H32', archive, offset=0)
            self.assertEqual(receipt.read_bytes(), b'competing evidence')
            self.assertFalse(output.exists())

    def test_lilu_uses_the_same_bytes_for_checksum_and_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'lilu.zip'
            with zipfile.ZipFile(archive, 'w') as stream:
                stream.writestr('Lilu.kext/Contents/Info.plist', b'info')
                stream.writestr('Lilu.kext/Contents/MacOS/Lilu', b'captured')
            content = archive.read_bytes()
            def changed_after_read(path):
                self.assertEqual(path, archive)
                archive.write_bytes(b'changed')
                return content
            with patch.object(Path, 'read_bytes', changed_after_read):
                files = boot.lilu_files(archive, hashlib.sha256(content).hexdigest())
            self.assertEqual(files['Lilu.kext/Contents/MacOS/Lilu'], b'captured')

    def test_lilu_archive_rejects_traversal_and_wrong_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'lilu.zip'
            with zipfile.ZipFile(archive, 'w') as stream:
                stream.writestr('Lilu.kext/../escape', b'value')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                boot.lilu_files(archive, '0' * 64)
            with self.assertRaisesRegex(ValueError, 'entry'):
                boot.lilu_files(archive, hashlib.sha256(archive.read_bytes()).hexdigest())

    def test_boot_preparation_keeps_the_verified_driver_when_inputs_change(self):
        from pyfatfs.PyFat import PyFat
        from pyfatfs.PyFatFS import PyFatFS
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original, output = root / 'original.raw', root / 'output.raw'
            original.touch()
            filesystem = PyFat()
            filesystem.mkfs(str(original), fat_type=PyFat.FAT_TYPE_FAT16, size=32 * 1024**2)
            filesystem.close()
            config = {'Kernel': {'Add': [{'BundlePath': 'Lilu.kext', 'Enabled': True},
                                        {'BundlePath': 'Other.kext', 'Enabled': True}]},
                      'Misc': {'Boot': {'ShowPicker': True}, 'Security': {'HaltLevel': 1}}}
            with PyFatFS(str(original)) as fat:
                fat.makedirs('/EFI/OC/Kexts/Other.kext')
                fat.writebytes('/EFI/OC/config.plist', plistlib.dumps(config))
                fat.writebytes('/EFI/OC/Kexts/Other.kext/sentinel', b'preserved')
            archive = root / 'lilu.zip'
            with zipfile.ZipFile(archive, 'w') as stream:
                stream.writestr('Lilu.kext/Contents/Info.plist', b'fixture-info')
                stream.writestr('Lilu.kext/Contents/MacOS/Lilu', b'fixture-lilu')
            lock = root / 'patches/reims-windows'
            lock.mkdir(parents=True)
            (lock / 'sources.json').write_text(json.dumps({'guest': {
                'lilu_sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}}))
            before = hashlib.sha256(original.read_bytes()).hexdigest()
            driver = root / 'driver'
            shutil.copytree(boot.DRIVER, driver, ignore=shutil.ignore_patterns('__pycache__'))
            captured = (driver / 'PvgTimingFix').read_bytes()
            lilu = boot.lilu_files
            def changed_during_preparation(*args):
                (driver / 'PvgTimingFix').write_bytes(b'changed after capture')
                return lilu(*args)
            with patch.object(boot, 'ROOT', root), patch.object(boot, 'DRIVER', driver), \
                    patch.object(boot, 'lilu_files', side_effect=changed_during_preparation):
                receipt = boot.prepare(original, output, '24H32', archive, offset=0)
            self.assertEqual(receipt['driver_sha256'], hashlib.sha256(captured).hexdigest())
            self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), before)
            with PyFatFS(str(output), read_only=True) as fat:
                updated = plistlib.loads(fat.readbytes('/EFI/OC/config.plist'))
                self.assertFalse(updated['Misc']['Boot']['ShowPicker'])
                self.assertEqual(fat.readbytes('/EFI/OC/Kexts/Other.kext/sentinel'), b'preserved')
                self.assertEqual(fat.readbytes('/EFI/OC/Kexts/PvgTimingFix.kext/Contents/MacOS/PvgTimingFix'),
                                 captured)
            with self.assertRaisesRegex(ValueError, 'overwritten'):
                boot.prepare(original, output, '24H32', archive, offset=0)


if __name__ == '__main__':
    unittest.main()
