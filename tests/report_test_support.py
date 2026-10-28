"""Shared isolated report fixtures for native and browser contracts."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = Path(os.environ.get("REPORT_TEST_PLUGINS", ROOT / "plugins"))

def published(output):
    pointer = output / 'current.json'
    return output / 'generations' / json.loads(pointer.read_text(encoding='utf-8'))['generation'] if pointer.exists() else output


class ReportFixture(unittest.TestCase):
    def diff_fixture(self, mode='ready'):
        def git(*args):
            return subprocess.check_output(['git', *args], cwd=self.project, stderr=subprocess.PIPE)
        git('init', '-q')
        git('config', 'user.name', 'Fixture')
        git('config', 'user.email', 'fixture@example.invalid')
        git('config', 'core.autocrlf', 'false')
        source = self.project / 'example.txt'
        source.write_bytes(b'context\nbefore <tag> & value\n')
        git('add', 'example.txt')
        git('commit', '-qm', 'base')
        source.write_bytes(b'context\nafter <tag> & value\n')
        fake = self.project / 'fake difft'
        record = dict(path='example.txt', language='Text', status='changed',
                      aligned_lines=[[0, 0], [1, 1]], chunks=[[{
                          'lhs': {'line_number': 1, 'changes': [{'start': 0, 'end': 6, 'content': 'before'}]},
                          'rhs': {'line_number': 1, 'changes': [{'start': 0, 'end': 5, 'content': 'after'}]}}]])
        fake.write_text('#!/usr/bin/env bash\n'
                        '[ "$DFT_UNSTABLE:$DFT_DISPLAY:$DFT_SKIP_UNCHANGED:$DFT_PARSE_ERROR_LIMIT" = "yes:json:true:100" ] || exit 42\n'
                        + ('exit 41\n' if mode == 'failed' else "printf '%s\\n' '" + json.dumps(record) + "'\n"),
                        encoding='utf-8', newline='\n')
        fake.chmod(0o755)
        output = self.project / 'output'
        self.command('diff-sharing', 'generate-diff-report.py', '--base-ref', 'HEAD', '--output-dir', output,
                     env={'DIFFTASTIC_COMMAND': 'missing-difftastic-fixture' if mode == 'unavailable' else str(fake),
                          'GIT_INCLUDE_UNCOMMITTED': 'true'})
        return output

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)

    def command(self, plugin, script, *args, env=None, success=True, cwd=None):
        environment = dict(os.environ)
        for key, value in (env or {}).items():
            if value is None:
                environment.pop(key, None)
            else:
                environment[key] = value
        result = subprocess.run([sys.executable, str(PLUGINS / plugin / 'scripts' / script), *map(str, args)],
                                cwd=cwd or self.project, env=environment, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

