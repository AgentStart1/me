import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bundle', ROOT / 'scripts/verify-viogpu-bundle.py')
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


class IntegrityTests(unittest.TestCase):
    def test_bundled_checksums(self):
        self.assertEqual(bundle.verify()['integrity'], 'PASS')

    def test_tampered_patch_rejected_before_source_preparation(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'bundle'
            shutil.copytree(bundle.BUNDLE, destination)
            with (destination / 'virglrenderer.patch').open('ab') as stream:
                stream.write(b'corrupted')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                bundle.verify(destination)

    def test_source_mismatch_leaves_operator_tree_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            file = source / 'hw/display/trace-events'
            file.parent.mkdir(parents=True)
            file.write_bytes(b'operator content')
            with self.assertRaisesRegex(ValueError, 'source mismatch'):
                bundle.verify(sources={'qemu': source})
            self.assertEqual(file.read_bytes(), b'operator content')

    def test_traversal_rejected(self):
        for name in ('../outside', '/absolute', 'C:/outside', 'sub\\outside'):
            with self.assertRaises(ValueError):
                bundle.relative_name(name)


if __name__ == '__main__':
    unittest.main()
