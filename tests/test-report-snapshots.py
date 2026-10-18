"""Publication and configuration invariants; temporary files only."""
import importlib.util
from contextlib import nullcontext
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = Path(os.environ.get('REPORT_TEST_PLUGINS', ROOT / 'plugins'))
sys.path.insert(0, str(ROOT / 'scripts/process-runtime'))
spec = importlib.util.spec_from_file_location('report_runtime', ROOT / 'scripts/report-sharing/report_runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class SnapshotTests(unittest.TestCase):
    def test_failure_retains_current_and_old_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'output'
            with runtime.report_snapshot(output) as (staged, _):
                (staged / 'index.html').write_text('first')
                (staged / 'asset.css').write_text('old asset')
            first = runtime.current_generation(output)
            for failure in ('build', 'pointer'):
                with self.assertRaises(OSError):
                    with patch.object(runtime, 'atomic_json', side_effect=OSError('publication failed')) if failure == 'pointer' else nullcontext():
                        with runtime.report_snapshot(output) as (staged, _):
                            (staged / 'index.html').write_text('second')
                            if failure == 'build':
                                raise OSError('build failed')
                self.assertEqual(runtime.current_generation(output), first)
                self.assertEqual((first / 'asset.css').read_text(), 'old asset')
            with runtime.report_snapshot(output) as (staged, _):
                (staged / 'index.html').write_text('second')
            self.assertNotEqual(runtime.current_generation(output), first)
            self.assertEqual((first / 'index.html').read_text(), 'first')

    def test_overlapping_builds_publish_complete_generations(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'output'
            with runtime.report_snapshot(output) as (outer, _):
                (outer / 'index.html').write_text('outer')
                with runtime.report_snapshot(output) as (inner, _):
                    (inner / 'index.html').write_text('inner')
                inner_generation = runtime.current_generation(output)
                self.assertEqual((inner_generation / 'index.html').read_text(), 'inner')
            self.assertEqual((runtime.current_generation(output) / 'index.html').read_text(), 'outer')
            self.assertEqual((inner_generation / 'index.html').read_text(), 'inner')

    def test_parser_does_not_change_working_directory(self):
        before = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            parser = runtime.output_parser('fixture', 'fixture')
            args = parser.parse_args(['--project-dir', directory, '--output-dir', 'caller-output'])
            self.assertEqual(args.project_dir, Path(directory).resolve())
            self.assertEqual(args.output_dir, before / 'caller-output')
            self.assertEqual(Path.cwd(), before)

    def test_repeated_collection_replaces_current_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            reports = project / 'build/reports/suite'
            reports.mkdir(parents=True)
            (reports / 'index.html').write_text('report')
            output = project / 'published'
            command = [sys.executable, str(PLUGINS / 'test-report-sharing/scripts/collect-test-results.py'),
                       '--project-dir', str(project), '--output-dir', str(output)]
            for _ in range(2):
                subprocess.run(command, check=True, capture_output=True)
                current = runtime.current_generation(output)
                self.assertEqual(len(list((current / 'reports').glob('*/index.html'))), 1)
                self.assertEqual(json.loads((current / 'reports/summary.json').read_text())['total_reports'], 1)
            old = current
            subprocess.run([sys.executable, str(PLUGINS / 'test-report-sharing/scripts/generate-report-site.py'),
                            '--project-dir', str(project), '--output-dir', str(output)], check=True, capture_output=True)
            self.assertEqual(runtime.current_generation(output), old)
            (reports / 'index.html').unlink()
            subprocess.run(command, check=True, capture_output=True)
            current = runtime.current_generation(output)
            self.assertEqual(list((current / 'reports').glob('*/index.html')), [])
            self.assertTrue((old / 'reports/suite/index.html').exists())

    def test_linked_assets_are_frozen_and_cycles_preserve_current(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            reports = project / 'build/reports/suite'
            reports.mkdir(parents=True)
            (reports / 'index.html').write_text('report')
            asset = project / 'asset.css'
            asset.write_text('first')
            try:
                (reports / 'style.css').symlink_to(asset)
            except OSError:
                self.skipTest('Symbolic links are unavailable')
            output = project / 'published'
            command = [sys.executable, str(PLUGINS / 'test-report-sharing/scripts/collect-test-results.py'),
                       '--project-dir', str(project), '--output-dir', str(output)]
            subprocess.run(command, check=True, capture_output=True)
            before = runtime.current_generation(output)
            asset.write_text('changed')
            frozen = before / 'reports/suite/style.css'
            self.assertFalse(frozen.is_symlink())
            self.assertEqual(frozen.read_text(), 'first')
            (reports / 'loop').symlink_to(reports, target_is_directory=True)
            failed = subprocess.run(command, capture_output=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(runtime.current_generation(output), before)
            self.assertEqual(frozen.read_text(), 'first')

    def test_process_runtime_copies(self):
        for plugin in ('android-emulator-profile', 'diff-sharing', 'test-report-sharing'):
            for name in ('command_tree.py', 'command-worker.py'):
                self.assertEqual((ROOT / 'scripts/process-runtime' / name).read_bytes(),
                                 (ROOT / 'plugins' / plugin / 'scripts' / name).read_bytes())


if __name__ == '__main__':
    unittest.main()
