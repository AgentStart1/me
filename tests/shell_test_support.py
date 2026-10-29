"""Private fixtures for tests that exercise real Bash compatibility boundaries."""
from pathlib import Path
import os
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('fixture_command_tree', ROOT / 'scripts/process-runtime/command_tree.py')
_runtime = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_runtime)


class ShellTestCase(unittest.TestCase):
    def setUp(self):
        self.bash = os.environ.get('BASH_TEST_BINARY') or shutil.which('bash')
        if not self.bash:
            self.skipTest('Bash required; set BASH_TEST_BINARY to Git Bash on Windows')
        self.directory = tempfile.TemporaryDirectory(prefix='shell-contract-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.env = dict(os.environ)
        self.env.update(QEMU_ALPINE_SKIP_MSYS2_PATH='1', PYTHONDONTWRITEBYTECODE='1')
        self.env['FIXTURE'] = self.path(self.root)
        self.env['FIXTURE_BIN'] = self.path(self.bin)
        self.env['REPOSITORY'] = self.path(ROOT)
        if os.name == 'nt':
            # Windows' python3 App Execution Alias is not an interpreter.
            self.env['TEST_PYTHON'] = self.path(sys.executable)
            self.mock('python3', 'exec "$TEST_PYTHON" "$@"')

    def path(self, path):
        value = str(path)
        if os.name == 'nt':
            return subprocess.check_output([self.bash, '-c', 'cygpath -u "$1"', 'path', value],
                                           encoding='utf-8', timeout=10).strip()
        return value

    def write(self, name, content, executable=False):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8', newline='\n')
        if executable:
            path.chmod(0o755)
        return path

    def mock(self, name, body):
        return self.write('bin/' + name, '#!/usr/bin/env bash\n' + body + '\n', True)

    def install_mocks(self, directory):
        for source in directory.iterdir():
            self.write('bin/' + source.name, source.read_text(encoding='utf-8'), True)

    def run_shell(self, body, *args, env=None, status=0, timeout=60):
        command = [self.bash, '-c',
                   'set -euo pipefail\nexport PATH="$FIXTURE_BIN:$PATH"\n' + body,
                   'contract', *map(str, args)]
        owner = _runtime.CommandTree()
        try:
            process = owner.start(command, cwd=self.root, env=self.env | (env or {}),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  encoding='utf-8', errors='replace')
            stdout, stderr = process.communicate(timeout=timeout)
            result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        finally:
            owner.stop()
        if status is not None:
            self.assertEqual(result.returncode, status, result.stdout + result.stderr)
        return result

    def read(self, name):
        return (self.root / name).read_text(encoding='utf-8')

    def start_shell(self, body, name='child', env=None):
        output = (self.root / (name + '.log')).open('wb')
        self.addCleanup(output.close)
        owner = _runtime.CommandTree()
        self.addCleanup(owner.stop)
        process = owner.start([self.bash, '-c',
                               'set -euo pipefail\nexport PATH="$FIXTURE_BIN:$PATH"\n'
                               'echo $$ > "$FIXTURE/$1.pid"\n' + body, 'contract', name],
                              cwd=self.root, env=self.env | (env or {}),
                              stdout=output, stderr=subprocess.STDOUT)
        self.wait_until(lambda: (self.root / (name + '.pid')).exists())
        return process

    def signal_shell(self, name='child'):
        self.run_shell('kill -TERM "$(cat "$FIXTURE/$1.pid")"', name)

    def assert_missing(self, name):
        self.assertFalse((self.root / name).exists(), name)

    def wait_until(self, condition, timeout=10):
        deadline = time.monotonic() + timeout
        while not condition():
            if time.monotonic() >= deadline:
                self.fail('Timed out waiting for fixture barrier')
            time.sleep(0.02)
