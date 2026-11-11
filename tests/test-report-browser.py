# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright==1.62.0"]
# ///
"""Real browser contracts against generated, isolated report snapshots."""
import os
import unittest
from playwright.sync_api import sync_playwright, expect

from report_test_support import ReportFixture, published


class BrowserFixture(ReportFixture):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        executable = os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE')
        cls.browser = cls.playwright.chromium.launch(
            headless=True, **({'executable_path': executable} if executable else {}))
        cls.addClassCleanup(cls.browser.close)


class DiffBrowserTests(BrowserFixture):
    def open_report(self, mode='ready'):
        output = self.diff_fixture(mode)
        page = self.browser.new_page()
        self.addCleanup(page.close)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        self.addCleanup(lambda: self.assertEqual(errors, []))
        page.goto((published(output) / 'diff/index.html').as_uri())
        return page

    def test_available_renderer_defaults_to_structural_content(self):
        page = self.open_report()
        expect(page.locator('#diff-renderer')).to_have_value('difftastic')
        expect(page.locator('#git-view')).to_be_hidden()
        expect(page.locator('#difftastic-stats')).to_be_visible()
        expect(page.locator('#git-stats')).to_be_hidden()
        output = page.locator('#difftastic-inline-output')
        expect(output).to_be_visible()
        expect(output.locator('.structural-file-header')).to_have_text('example.txt · Text')
        expect(output.locator('.structural-code')).to_have_text([
            'context', 'before <tag> & value', 'after <tag> & value'])
        expect(output.locator('.structural-change-remove')).to_have_text('before')
        expect(output.locator('.structural-change-add')).to_have_text('after')
        expect(output.locator('tag')).to_have_count(0)
        # Computed styling proves the copied stylesheet is loaded, not just linked.
        expect(output.locator('.structural-change-add')).to_have_css('color', 'rgb(25, 107, 53)')
        expect(output.locator('.structural-change-add')).to_have_css('font-weight', '700')

    def test_renderer_switch_updates_content_controls_and_summary(self):
        page = self.open_report()
        page.locator('#diff-renderer').select_option('git')
        expect(page.locator('#git-view')).to_be_visible()
        expect(page.locator('#git-view')).to_contain_text('after <tag> & value')
        expect(page.locator('#git-view')).to_contain_text('before <tag> & value')
        expect(page.locator('#git-view tag')).to_have_count(0)
        expect(page.locator('#difftastic-view')).to_be_hidden()
        expect(page.locator('#difftastic-layout-control')).to_be_hidden()
        expect(page.locator('#git-stats')).to_be_visible()
        expect(page.locator('#difftastic-stats')).to_be_hidden()
        page.locator('#diff-renderer').select_option('difftastic')
        expect(page.locator('#git-view')).to_be_hidden()
        expect(page.locator('#difftastic-inline-output')).to_be_visible()
        expect(page.locator('#difftastic-layout-control')).to_be_visible()
        expect(page.locator('#difftastic-stats')).to_be_visible()

    def test_layout_switch_renders_paired_sources_and_returns_inline(self):
        page = self.open_report()
        page.locator('#difftastic-layout').select_option('side-by-side')
        expect(page.locator('#difftastic-inline-output')).to_be_hidden()
        output = page.locator('#difftastic-side-by-side-output')
        expect(output).to_be_visible()
        expect(page.locator('#difftastic-display-value')).to_have_text('Side by Side')
        rows = output.locator('.structural-row')
        expect(rows).to_have_count(2)
        expect(rows.nth(0).locator('.structural-code')).to_have_text(['context', 'context'])
        expect(rows.nth(1).locator('.structural-code')).to_have_text(['before <tag> & value', 'after <tag> & value'])
        expect(rows.nth(1).locator('.structural-change-remove')).to_have_text('before')
        expect(rows.nth(1).locator('.structural-change-add')).to_have_text('after')
        page.locator('#difftastic-layout').select_option('inline')
        expect(output).to_be_hidden()
        expect(page.locator('#difftastic-inline-output')).to_be_visible()
        expect(page.locator('#difftastic-display-value')).to_have_text('Inline')

    def assert_git_fallback(self, mode):
        page = self.open_report(mode)
        expect(page.locator('#diff-renderer')).to_have_value('git')
        expect(page.locator('#diff-renderer option[value=difftastic]')).to_be_disabled()
        expect(page.locator('#git-view')).to_be_visible()
        expect(page.locator('#git-view')).to_contain_text('after <tag> & value')
        expect(page.locator('#git-view tag')).to_have_count(0)
        expect(page.locator('#difftastic-view')).to_be_hidden()
        expect(page.locator('#difftastic-layout-control')).to_be_hidden()
        expect(page.locator('#git-stats')).to_be_visible()

    def test_missing_difftastic_disables_structural_renderer(self):
        self.assert_git_fallback('unavailable')

    def test_failed_difftastic_displays_git_fallback(self):
        self.assert_git_fallback('failed')


class ThemeBrowserTests(BrowserFixture):
    def report_paths(self):
        output = self.diff_fixture()
        self.command('diff-sharing', 'generate-diff-site.py', '--output-dir', output)
        diff = published(output)
        reports = self.project / 'build/test-results'
        reports.mkdir(parents=True)
        (reports / 'TEST-example.xml').write_text('<testsuite tests="1" failures="0"/>')
        tests = self.project / 'test-output'
        self.command('test-report-sharing', 'collect-test-results.py', '--project-dir', self.project,
                     '--output-dir', tests)
        return [diff / 'index.html', diff / 'diff/index.html', published(tests) / 'index.html']

    def assert_theme(self, page, scheme):
        expect(page.locator('body')).to_have_css(
            'background-color', 'rgb(20, 25, 34)' if scheme == 'dark' else 'rgb(245, 245, 245)')
        expect(page.locator('body')).to_have_css(
            'color', 'rgb(230, 237, 245)' if scheme == 'dark' else 'rgb(37, 51, 71)')
        # Measure rendered text against its composited ancestor background.
        failures = page.evaluate(r"""() => {
            const rgb = value => (value.match(/[\d.]+/g) || []).map(Number);
            const luminance = c => c.slice(0, 3).map(v => {
                v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4;
            }).reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
            return [...document.querySelectorAll('body *')].flatMap(el => {
                if (!el.getClientRects().length || ['SCRIPT', 'STYLE', 'OPTION'].includes(el.tagName)
                    || ![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return [];
                const background = node => {
                    if (!node) return [255, 255, 255];
                    const c = rgb(getComputedStyle(node).backgroundColor);
                    const behind = background(node.parentElement);
                    const alpha = c.length === 4 ? c[3] : 1;
                    return c.slice(0, 3).map((v, i) => v * alpha + behind[i] * (1 - alpha));
                };
                const fg = luminance(rgb(getComputedStyle(el).color));
                const bg = luminance(background(el));
                const ratio = (Math.max(fg, bg) + .05) / (Math.min(fg, bg) + .05);
                return ratio >= 4.5 ? [] : [{element: el.className, ratio}];
            });
        }""")
        self.assertEqual(failures, [])

    def test_generated_reports_follow_initial_system_preference(self):
        paths = self.report_paths()
        for path in paths:
            for scheme in ('light', 'dark'):
                with self.subTest(report=path.name, scheme=scheme):
                    page = self.browser.new_page(color_scheme=scheme)
                    try:
                        page.goto(path.as_uri())
                        self.assert_theme(page, scheme)
                    finally:
                        page.close()

    def test_open_reports_follow_system_changes_and_reload(self):
        for path in self.report_paths():
            with self.subTest(report=str(path)):
                page = self.browser.new_page(color_scheme='light')
                try:
                    page.goto(path.as_uri())
                    for scheme in ('dark', 'light', 'dark'):
                        page.emulate_media(color_scheme=scheme)
                        self.assert_theme(page, scheme)
                    page.reload()
                    self.assert_theme(page, 'dark')
                    if page.locator('#diff-renderer').count():
                        page.locator('#diff-renderer').select_option('git')
                        self.assert_theme(page, 'dark')
                        page.emulate_media(color_scheme='light')
                        self.assert_theme(page, 'light')
                finally:
                    page.close()

    def test_empty_test_report_text_follows_system_theme(self):
        output = self.project / 'empty-output'
        self.command('test-report-sharing', 'collect-test-results.py', '--project-dir', self.project,
                     '--output-dir', output)
        for scheme in ('light', 'dark'):
            with self.subTest(scheme=scheme):
                page = self.browser.new_page(color_scheme=scheme)
                try:
                    page.goto((published(output) / 'index.html').as_uri())
                    expect(page.locator('.report-links')).to_contain_text('No reports found')
                    self.assert_theme(page, scheme)
                finally:
                    page.close()

    def test_failed_renderer_note_follows_system_theme(self):
        output = self.diff_fixture('failed')
        for scheme in ('light', 'dark'):
            with self.subTest(scheme=scheme):
                page = self.browser.new_page(color_scheme=scheme)
                try:
                    page.goto((published(output) / 'diff/index.html').as_uri())
                    expect(page.locator('#diff-renderer')).to_have_value('git')
                    expect(page.locator('.view-note')).to_be_visible()
                    self.assert_theme(page, scheme)
                    page.locator('.back-link').focus()
                    expect(page.locator('.back-link')).to_have_css('outline-style', 'solid')
                finally:
                    page.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
