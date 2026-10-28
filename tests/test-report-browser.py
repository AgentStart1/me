# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright==1.62.0"]
# ///
"""Real browser contracts against generated, isolated report snapshots."""
import os
import unittest
from playwright.sync_api import sync_playwright, expect

from report_test_support import ReportFixture, published


class DiffBrowserTests(ReportFixture):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        executable = os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE')
        cls.browser = cls.playwright.chromium.launch(
            headless=True, **({'executable_path': executable} if executable else {}))
        cls.addClassCleanup(cls.browser.close)

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
        expect(output.locator('.structural-change-add')).to_have_css('color', 'rgb(143, 226, 52)')
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


if __name__ == '__main__':
    unittest.main(verbosity=2)
