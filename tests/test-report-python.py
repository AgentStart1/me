"""Native entrypoint regressions using temporary reports and Git repositories."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import shutil
from itertools import product

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = Path(os.environ.get('REPORT_TEST_PLUGINS', ROOT / 'plugins'))
PLUGIN = sys.argv.pop(1) if len(sys.argv) > 1 and sys.argv[1] in ('diff-sharing', 'test-report-sharing') else None


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)

    def command(self, plugin, script, *args, env=None, success=True, cwd=None):
        environment = dict(os.environ)
        environment.update(env or {})
        result = subprocess.run([sys.executable, str(PLUGINS / plugin / 'scripts' / script), *map(str, args)],
                                cwd=cwd or self.project, env=environment, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def test_bundled_runtime(self):
        source = (ROOT / 'scripts/report-sharing/report_runtime.py').read_bytes()
        for name in ('diff-sharing', 'test-report-sharing'):
            self.assertEqual(source, (ROOT / 'plugins' / name / 'scripts/report_runtime.py').read_bytes())

    @unittest.skipIf(PLUGIN == 'diff-sharing', 'Other plugin')
    def test_collection_paths_duplicates_and_recursive_output(self):
        root = self.project / 'custom space & reports'
        (root / 'nested').mkdir(parents=True)
        (root / 'index.html').write_text('<html>report</html>', encoding='utf-8')
        (root / 'nested/index.html').write_text('child', encoding='utf-8')
        (root / 'TEST-one.xml').write_text('<testsuite/>', encoding='utf-8')
        other = self.project / 'other'
        other.mkdir()
        (other / 'TEST-one.xml').write_text('<testsuite name="other"/>', encoding='utf-8')
        output = self.project / 'output space & results'
        self.command('test-report-sharing', 'collect-test-results.py', '--test-dir', root,
                     '--test-dir', root / 'nested', '--test-dir', other, '--output-dir', output)
        summary = json.loads((output / 'reports/summary.json').read_text())
        self.assertEqual((summary['total_reports'], summary['xml_files']), (1, 2))
        self.command('test-report-sharing', 'generate-report-site.py', '--output-dir', output)
        self.assertEqual((output / 'index.html').read_text(encoding='utf-8').count('(JUnit XML)'), 2)
        self.command('test-report-sharing', 'collect-test-results.py', '--test-dir', root,
                     '--output-dir', root / 'inside', success=False)
        self.assertFalse((root / 'inside').exists())

    @unittest.skipIf(PLUGIN == 'diff-sharing', 'Other plugin')
    def test_bounded_scan_and_url_encoding(self):
        root = self.project / 'xml'
        shallow = root / 'a/b/c'
        deep = shallow / 'd'
        deep.mkdir(parents=True)
        (shallow / 'TEST-visible.xml').write_text('visible')
        (deep / 'TEST-hidden.xml').write_text('hidden')
        output = self.project / 'output'
        self.command('test-report-sharing', 'collect-test-results.py', '--test-dir', root, '--output-dir', output)
        self.assertEqual(len(list((output / 'test-results').glob('*.xml'))), 1)
        report = output / 'reports' / 'name # & quote'
        report.mkdir()
        (report / 'index.html').write_text('report')
        self.command('test-report-sharing', 'generate-report-site.py', '--output-dir', output)
        page = (output / 'index.html').read_text(encoding='utf-8')
        self.assertIn('name%20%23%20%26%20quote/index.html', page)
        self.assertIn('&amp;', page)

    @unittest.skipIf(PLUGIN == 'test-report-sharing', 'Other plugin')
    def test_git_modes_binary_and_invalid_refs(self):
        def git(*args):
            return subprocess.check_output(['git', *args], cwd=self.project, stderr=subprocess.PIPE)
        git('init', '-q')
        git('config', 'user.name', 'Fixture')
        git('config', 'user.email', 'fixture@example.invalid')
        (self.project / 'space & file.txt').write_text('before\n', encoding='utf-8')
        git('add', '.')
        git('commit', '-qm', 'base')
        git('tag', 'base')
        (self.project / 'space & file.txt').write_text('after <tag> & value\n', encoding='utf-8')
        (self.project / 'binary.bin').write_bytes(b'\0binary')
        git('add', '.')
        git('commit', '-qm', 'change')
        output = self.project / 'output with spaces'
        self.command('diff-sharing', 'generate-diff-report.py', '--output-dir', output, '--base-ref', 'base',
                     env={'GIT_INCLUDE_UNCOMMITTED': 'false', 'DIFFTASTIC_COMMAND': 'missing-fixture-tool'})
        stats = json.loads((output / 'diff/stats.json').read_text())
        self.assertEqual((stats['files_changed'], stats['insertions'], stats['deletions']), (2, 1, 1))
        self.assertIn('&lt;tag&gt; &amp; value', (output / 'diff/index.html').read_text(encoding='utf-8'))
        self.command('diff-sharing', 'generate-diff-report.py', '--base-ref', 'base', '--compare-ref', 'missing',
                     env={'GIT_INCLUDE_UNCOMMITTED': 'false'}, success=False)
        self.command('diff-sharing', 'generate-diff-report.py', '--base-ref', 'base',
                     env={'DIFFTASTIC_WIDTH': '0'}, success=False)
        self.command('diff-sharing', 'generate-diff-site.py', '--output-dir', output)
        self.assertNotIn('@@', (output / 'index.html').read_text(encoding='utf-8'))

    def test_argument_validation(self):
        for plugin in [PLUGIN] if PLUGIN else ('diff-sharing', 'test-report-sharing'):
            self.command(plugin, 'start-ngrok.py', '--port', '65536', success=False)
            self.command(plugin, 'start-ngrok.py', '--output-dir', success=False)

    @unittest.skipIf(PLUGIN == 'test-report-sharing', 'Other plugin')
    def test_structural_sources_pretty_json_and_rename(self):
        if not shutil.which('bash'):
            self.skipTest('Bash fixture unavailable')
        def git(*args):
            return subprocess.check_output(['git', *args], cwd=self.project, stderr=subprocess.PIPE)
        git('init', '-q')
        git('config', 'user.name', 'Fixture')
        git('config', 'user.email', 'fixture@example.invalid')
        source = self.project / 'old # name.py'
        before = 'value = 1\n' + '# context\n' * 10
        source.write_text(before, encoding='utf-8')
        git('add', '.'); git('commit', '-qm', 'base')
        source.rename(self.project / 'new # name.py')
        (self.project / 'new # name.py').write_text(before.replace('1', '2'), encoding='utf-8')
        git('add', '.'); git('commit', '-qm', 'rename')
        fake = self.project / 'fake difft'
        fake.write_text('#!/usr/bin/env bash\ncat <<\'JSON\'\n{\n  "path": "new # name.py",\n  "status": "changed"\n}\nJSON\n', encoding='utf-8', newline='\n')
        fake.chmod(0o755)
        output = self.project / 'output'
        self.command('diff-sharing', 'generate-diff-report.py', '--base-ref', 'HEAD~1', '--output-dir', output,
                     env={'GIT_INCLUDE_UNCOMMITTED': 'false', 'DIFFTASTIC_COMMAND': str(fake)})
        records = (output / 'diff/difftastic.jsonl').read_text().splitlines()
        self.assertEqual(len(records), 1)
        old, new, payload = map(base64.b64decode, records[0].split('\t'))
        self.assertEqual(old.decode().replace('\r\n', '\n'), before)
        self.assertEqual(new.decode().replace('\r\n', '\n'), before.replace('1', '2'))
        self.assertEqual(json.loads(payload)['status'], 'changed')
        self.assertEqual(json.loads((output / 'diff/stats.json').read_text())['files_changed'], 1)

    def init_structural_fixture(self):
        if not shutil.which('bash'):
            self.skipTest('Bash fixture unavailable')
        def git(*args):
            return subprocess.check_output(['git', *args], cwd=self.project, stderr=subprocess.PIPE)
        git('init', '-q')
        git('config', 'user.name', 'Fixture')
        git('config', 'user.email', 'fixture@example.invalid')
        git('config', 'core.autocrlf', 'false')
        fake = self.project / 'fake difft'
        fake.write_text('#!/usr/bin/env bash\nprintf \'{"status":"changed"}\\n\'\n', encoding='utf-8', newline='\n')
        fake.chmod(0o755)
        return git, fake

    @unittest.skipIf(PLUGIN == 'test-report-sharing', 'Other plugin')
    def test_worktree_sources_from_repository_subdirectory(self):
        git, fake = self.init_structural_fixture()
        directory = self.project / 'nested space'
        directory.mkdir()
        source = directory / 'example.py'
        source.write_bytes(b'value = 1\n')
        git('add', 'nested space'); git('commit', '-qm', 'base')
        source.write_bytes(b'value = 2\n')
        for relative in ('false', 'true'):
            with self.subTest(diff_relative=relative):
                git('config', 'diff.relative', relative)
                output = self.project / ('output-' + relative)
                self.command('diff-sharing', 'generate-diff-report.py', '--base-ref', 'HEAD', '--output-dir', output,
                             cwd=directory, env={'GIT_INCLUDE_UNCOMMITTED': 'true', 'DIFFTASTIC_COMMAND': str(fake)})
                records = (output / 'diff/difftastic.jsonl').read_text().splitlines()
                self.assertEqual(len(records), 1)
                old, new, _ = map(base64.b64decode, records[0].split('\t'))
                self.assertEqual(old, b'value = 1\n')
                self.assertEqual(new, b'value = 2\n')

    @unittest.skipIf(PLUGIN == 'test-report-sharing', 'Other plugin')
    def test_committed_deletion_does_not_capture_worktree_file(self):
        git, fake = self.init_structural_fixture()
        source = self.project / 'example.py'
        source.write_bytes(b'value = 1\n')
        git('add', 'example.py'); git('commit', '-qm', 'base')
        git('tag', 'base')
        git('rm', 'example.py'); git('commit', '-qm', 'delete')
        source.write_bytes(b'outside-comparison-fixture\n')
        for mode in ('false', 'true'):
            with self.subTest(include_worktree=mode):
                output = self.project / ('output-' + mode)
                self.command('diff-sharing', 'generate-diff-report.py', '--base-ref', 'base', '--compare-ref', 'HEAD',
                             '--output-dir', output, env={'GIT_INCLUDE_UNCOMMITTED': mode, 'DIFFTASTIC_COMMAND': str(fake)})
                records = (output / 'diff/difftastic.jsonl').read_text().splitlines()
                self.assertEqual(len(records), 1)
                old, new, _ = map(base64.b64decode, records[0].split('\t'))
                self.assertEqual(old, b'value = 1\n')
                self.assertEqual(new, b'')
                page = (output / 'diff/index.html').read_text(encoding='utf-8')
                self.assertNotIn(base64.b64encode(source.read_bytes()).decode(), page)

    @unittest.skipIf(PLUGIN == 'test-report-sharing', 'Other plugin')
    def test_gitlink_add_update_delete_preserve_regular_file_diffs(self):
        git, fake = self.init_structural_fixture()
        source = self.project / 'example.py'
        source.write_bytes(b'value = 0\n')
        git('add', 'example.py'); git('commit', '-qm', 'base')
        git('tag', 'base')
        # These gitlink commits deliberately do not exist in the parent object DB.
        first, second = '1' * 40, '2' * 40
        for tag, oid, value in (('added', first, 1), ('updated', second, 2), ('deleted', None, 3)):
            if oid:
                git('update-index', '--add', '--cacheinfo', f'160000,{oid},module')
            else:
                git('update-index', '--force-remove', 'module')
            source.write_bytes(f'value = {value}\n'.encode())
            git('add', 'example.py'); git('commit', '-qm', tag); git('tag', tag)
        for base, compare, old, new, value in (
                ('base', 'added', b'', f'Subproject commit {first}\n'.encode(), 1),
                ('added', 'updated', f'Subproject commit {first}\n'.encode(), f'Subproject commit {second}\n'.encode(), 2),
                ('updated', 'deleted', f'Subproject commit {second}\n'.encode(), b'', 3)):
            with self.subTest(change=compare):
                output = self.project / ('output-' + compare)
                self.command('diff-sharing', 'generate-diff-report.py', '--base-ref', base, '--compare-ref', compare,
                             '--output-dir', output, env={'GIT_INCLUDE_UNCOMMITTED': 'false', 'DIFFTASTIC_COMMAND': str(fake)})
                records = (output / 'diff/difftastic.jsonl').read_text().splitlines()
                pairs = {tuple(map(base64.b64decode, record.split('\t')[:2])) for record in records}
                self.assertEqual(pairs, {(old, new), (f'value = {value - 1}\n'.encode(), f'value = {value}\n'.encode())})
                self.assertNotIn('Difftastic failed to generate', (output / 'diff/index.html').read_text(encoding='utf-8'))

    @unittest.skipIf(PLUGIN == 'test-report-sharing', 'Other plugin')
    def test_gitlink_worktree_commit_and_dirty_state(self):
        git, fake = self.init_structural_fixture()
        module = self.project / 'module [x] space'
        module.mkdir()
        git('-C', str(module), 'init', '-q')
        git('-C', str(module), 'config', 'user.name', 'Fixture')
        git('-C', str(module), 'config', 'user.email', 'fixture@example.invalid')
        git('-C', str(module), 'config', 'core.autocrlf', 'false')
        (module / 'code.py').write_bytes(b'value = 1\n')
        git('-C', str(module), 'add', 'code.py'); git('-C', str(module), 'commit', '-qm', 'first')
        first = git('-C', str(module), 'rev-parse', 'HEAD').strip()
        source = self.project / 'example.py'
        source.write_bytes(b'value = 1\n')
        git('add', 'example.py')
        git('update-index', '--add', '--cacheinfo', f'160000,{first.decode()},{module.name}')
        git('commit', '-qm', 'base')
        git('config', 'diff.ignoreSubmodules', 'none')
        (module / 'code.py').write_bytes(b'value = 2\n')
        git('-C', str(module), 'add', 'code.py'); git('-C', str(module), 'commit', '-qm', 'second')
        second = git('-C', str(module), 'rev-parse', 'HEAD').strip()
        source.write_bytes(b'value = 2\n')
        nested = self.project / 'nested'
        nested.mkdir()
        for dirty, location, relative in product((False, True), ('root', 'nested'), ('false', 'true')):
            with self.subTest(dirty=dirty, location=location, diff_relative=relative):
                (module / 'code.py').write_bytes(b'value = 3\n' if dirty else b'value = 2\n')
                git('config', 'diff.relative', relative)
                output = self.project / f'output-{dirty}-{location}-{relative}'
                self.command('diff-sharing', 'generate-diff-report.py', '--base-ref', 'HEAD', '--output-dir', output,
                             cwd=nested if location == 'nested' else self.project,
                             env={'GIT_INCLUDE_UNCOMMITTED': 'true', 'DIFFTASTIC_COMMAND': str(fake)})
                records = (output / 'diff/difftastic.jsonl').read_text().splitlines()
                pairs = {tuple(map(base64.b64decode, record.split('\t')[:2])) for record in records}
                self.assertEqual(pairs, {(b'Subproject commit ' + first + b'\n',
                                         b'Subproject commit ' + second + (b'-dirty' if dirty else b'') + b'\n'),
                                        (b'value = 1\n', b'value = 2\n')})


if __name__ == '__main__':
    unittest.main()
