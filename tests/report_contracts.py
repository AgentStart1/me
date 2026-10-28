"""Structured contracts migrated from report Shell suites."""
import base64
from html.parser import HTMLParser
import json
import os
import subprocess
from urllib.parse import unquote
import xml.etree.ElementTree as ET

from report_test_support import PLUGINS, ReportFixture, published


class Page(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.elements = []
        self.text = []
        self.feed(path.read_text(encoding='utf-8'))

    def handle_starttag(self, tag, attributes):
        self.elements.append((tag, dict(attributes)))

    def handle_data(self, text):
        self.text.append(text)

    def links(self):
        return [attrs['href'] for tag, attrs in self.elements if tag == 'a']


class CollectionContracts(ReportFixture):
    def collect(self, *args, **kwargs):
        output = self.project / 'output'
        self.command('test-report-sharing', 'collect-test-results.py', '--output-dir', output, *args, **kwargs)
        return published(output)

    def test_legacy_directory_alias_deduplicates_nested_html(self):
        root = self.project / 'custom'
        (root / 'nested').mkdir(parents=True)
        (root / 'index.html').write_text('parent', encoding='utf-8')
        (root / 'nested/index.html').write_text('child', encoding='utf-8')
        result = self.collect(env={'REPORT_DIRS': 'custom:custom/nested', 'TEST_RESULT_DIRS': None})
        summary = json.loads((result / 'reports/summary.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['total_reports'], 1)
        self.assertEqual(len(summary['report_directories']), 1)
        copied = result / summary['report_directories'][0]
        self.assertEqual((copied / 'index.html').read_text(encoding='utf-8'), 'parent')
        self.assertEqual((copied / 'nested/index.html').read_text(encoding='utf-8'), 'child')

    def test_duplicate_xml_basenames_retain_distinct_contents(self):
        for directory, name in [('build/test-results/test', 'first'), ('extra/nested', 'second')]:
            root = self.project / directory
            root.mkdir(parents=True)
            (root / 'TEST-same.xml').write_text(f'<testsuite name="{name}"/>', encoding='utf-8')
        result = self.collect('--test-dir', 'extra')
        summary = json.loads((result / 'reports/summary.json').read_text(encoding='utf-8'))
        files = list((result / 'test-results').glob('*.xml'))
        self.assertEqual(summary['xml_files'], 2)
        self.assertEqual(len(files), 2)
        self.assertEqual({ET.parse(file).getroot().attrib['name'] for file in files}, {'first', 'second'})

    def test_empty_collection_summary(self):
        result = self.collect()
        summary = json.loads((result / 'reports/summary.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['total_reports'], 0)
        self.assertEqual(summary['xml_files'], 0)
        self.assertEqual(summary['report_directories'], [])

    def test_site_links_nested_xml_artifacts(self):
        root = self.project / 'custom/nested'
        root.mkdir(parents=True)
        for name in ('first', 'second'):
            (root / f'TEST-{name}.xml').write_text(f'<testsuite name="{name}"/>', encoding='utf-8')
        result = self.collect('--test-dir', 'custom')
        page = Page(result / 'index.html')
        links = [link for link in page.links() if link.endswith('.xml')]
        self.assertEqual(len(links), 2)
        self.assertEqual({ET.parse(result / unquote(link)).getroot().attrib['name'] for link in links}, {'first', 'second'})

    def test_empty_site_has_no_diff_section(self):
        output = self.project / 'output'
        self.command('test-report-sharing', 'generate-report-site.py', '--output-dir', output)
        page = Page(published(output) / 'index.html')
        self.assertIn('No reports found. Run your tests first to generate reports.', ''.join(page.text))
        self.assertNotIn('Code Diff', ''.join(page.text))
        self.assertEqual(page.links(), [])

    def test_site_encodes_links_and_escapes_labels(self):
        output = self.project / 'output'
        # Numeric entities remain meaningful after title-casing and are valid
        # filename characters on Windows as well as Unix.
        name = "name # & ' &#60;b&#62;"
        report = output / 'reports' / name
        report.mkdir(parents=True)
        (report / 'index.html').write_text('report', encoding='utf-8')
        self.command('test-report-sharing', 'generate-report-site.py', '--output-dir', output)
        result = published(output)
        page = Page(result / 'index.html')
        self.assertEqual(page.links(), ['reports/name%20%23%20%26%20%27%20%26%2360%3Bb%26%2362%3B/index.html'])
        self.assertIn(name.title(), ''.join(page.text))
        self.assertEqual((result / unquote(page.links()[0])).read_text(encoding='utf-8'), 'report')


class ShellContracts(ReportFixture):
    def assert_dispatch(self, plugin, script):
        interpreter = self.project / 'record interpreter.sh'
        log = self.project / 'arguments.bin'
        interpreter.write_text(
            '#!/usr/bin/env bash\n'
            'if [[ "${1:-}" == -c ]]; then exit 0; fi\n'
            '# Normalize only the script path for native Windows assertions.\n'
            'if command -v cygpath >/dev/null 2>&1; then\n'
            '    target=$(cygpath -m "$1")\n'
            'else target=$1; fi\n'
            'shift\n'
            'printf "%s\\0" "$target" "$@" > "$REPORT_LAUNCH_LOG"\n'
            'exit "$REPORT_LAUNCH_STATUS"\n', encoding='utf-8', newline='\n')
        interpreter.chmod(0o755)
        entry = PLUGINS / plugin / 'scripts' / script
        arguments = ['--output-dir', 'path with spaces', '', 'literal * [x]', 'Unicode 中文']
        for status in (0, 37):
            with self.subTest(exit_status=status):
                log.unlink(missing_ok=True)
                environment = dict(os.environ, PYTHON_COMMAND=interpreter.as_posix(),
                                   REPORT_LAUNCH_LOG=log.as_posix(), REPORT_LAUNCH_STATUS=str(status))
                bash = os.environ.get('BASH_TEST_BINARY', 'bash')
                result = subprocess.run([bash, str(entry.with_suffix('.sh')), *arguments],
                                        env=environment, capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(result.returncode, status, result.stdout + result.stderr)
                recorded = log.read_bytes().decode('utf-8').split('\0')
                self.assertEqual(os.path.normcase(recorded[0]), os.path.normcase(entry.with_suffix('.py').as_posix()))
                self.assertEqual(recorded[1:], [*arguments, ''])

    def test_diff_report_shell_dispatch(self):
        self.assert_dispatch('diff-sharing', 'generate-diff-report')

    def test_diff_site_shell_dispatch(self):
        self.assert_dispatch('diff-sharing', 'generate-diff-site')

    def test_collection_shell_dispatch(self):
        self.assert_dispatch('test-report-sharing', 'collect-test-results')

    def test_report_site_shell_dispatch(self):
        self.assert_dispatch('test-report-sharing', 'generate-report-site')


class DiffContracts(ReportFixture):
    def stats(self, mode):
        result = published(self.diff_fixture(mode))
        return result, json.loads((result / 'diff/stats.json').read_text(encoding='utf-8'))

    def test_missing_difftastic_reports_unavailable(self):
        _, stats = self.stats('unavailable')
        self.assertIs(stats['difftastic_available'], False)
        self.assertEqual(stats['difftastic_status'], 'unavailable')
        self.assertEqual((stats['files_changed'], stats['insertions'], stats['deletions']), (1, 1, 1))

    def test_available_difftastic_configuration_and_source_payload(self):
        result, stats = self.stats('ready')
        self.assertIs(stats['difftastic_available'], True)
        self.assertEqual(stats['difftastic_status'], 'ready')
        self.assertIs(stats['difftastic_skip_unchanged'], True)
        self.assertEqual(stats['difftastic_parse_error_limit'], 100)
        records = (result / 'diff/difftastic.jsonl').read_text(encoding='utf-8').splitlines()
        self.assertEqual(len(records), 1)
        before, after, data = map(base64.b64decode, records[0].split('\t'))
        self.assertEqual(before, b'context\nbefore <tag> & value\n')
        self.assertEqual(after, b'context\nafter <tag> & value\n')
        self.assertEqual(json.loads(data)['aligned_lines'], [[0, 0], [1, 1]])

    def test_failed_difftastic_retains_git_artifact(self):
        result, stats = self.stats('failed')
        self.assertEqual(stats['difftastic_status'], 'failed')
        self.assertFalse((result / 'diff/difftastic.jsonl').exists())
        page = Page(result / 'diff/git-diff-content.html')
        self.assertIn('after <tag> & value', ''.join(page.text))
        self.assertFalse(any(tag == 'tag' for tag, _ in page.elements))

    def test_diff_site_publishes_summary_and_stylesheets(self):
        output = self.diff_fixture('unavailable')
        self.command('diff-sharing', 'generate-diff-site.py', '--output-dir', output)
        result = published(output)
        page = Page(result / 'index.html')
        self.assertIn('1 file(s) changed. Git line stats:', ''.join(page.text))
        self.assertIn('diff/index.html', page.links())
        for path in ('index.html', 'diff/index.html'):
            asset_page = Page(result / path)
            styles = [a['href'] for tag, a in asset_page.elements if tag == 'link' and a.get('rel') == 'stylesheet']
            self.assertEqual(len(styles), 1)
            self.assertTrue((result / path).parent.joinpath(styles[0]).is_file())


class TemplateContracts(ReportFixture):
    def test_page_bodies_remain_owned_by_templates(self):
        for script in ('generate-diff-report', 'generate-diff-site'):
            self.assertNotIn('<!DOCTYPE html>', (PLUGINS / 'diff-sharing/scripts' / f'{script}.sh').read_text(encoding='utf-8'))
        self.assertIn('@@FILES_CHANGED@@', (PLUGINS / 'diff-sharing/templates/diff-report.html').read_text(encoding='utf-8'))
        self.assertIn('<!-- @@DIFF_SECTION@@ -->', (PLUGINS / 'diff-sharing/templates/diff-site.html').read_text(encoding='utf-8'))
        self.assertNotIn('@@DIFF_SECTION@@', (PLUGINS / 'test-report-sharing/templates/report-site.html').read_text(encoding='utf-8'))
