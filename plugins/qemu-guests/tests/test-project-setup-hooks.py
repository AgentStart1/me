"""Project setup scripts preserve arguments, private logs, failures and source fingerprints."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from project_setup_hooks import prepare_host, validate
from test_requirements import load


class SetupHookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def test_host_preparation_preserves_arguments_and_private_output(self):
        command = [sys.executable, '-c', 'import sys; assert sys.argv[1]=="one two"; print("private fixture")', 'one two']
        prepare_host([{'command': command, 'cwd': str(self.root), 'timeout_seconds': 15}], self.root / 'logs')
        self.assertIn('private fixture', (self.root / 'logs/host-prepare-0.log').read_text())

    def test_host_failure_is_not_silently_ignored(self):
        with self.assertRaisesRegex(RuntimeError, 'Host preparation hook failed'):
            prepare_host([{'command': [sys.executable, '-c', 'import sys; sys.exit(23)'],
                           'cwd': str(self.root), 'timeout_seconds': 15}], self.root / 'logs')

    def test_hook_timeout_must_be_bounded_before_execution(self):
        with self.assertRaisesRegex(ValueError, 'timeout'):
            validate({'host_prepare': [{'command': ['fixture'], 'cwd': '.', 'timeout_seconds': 0}]}, self.root)

    def test_host_timeout_stops_the_owned_command_scope(self):
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            prepare_host([{'command': [sys.executable, '-c', 'import time; time.sleep(20)'],
                           'cwd': str(self.root), 'timeout_seconds': 1}], self.root / 'logs')

    def test_guest_timeout_stops_the_owned_setup_process(self):
        import os
        runner = self.root / 'run-setup-hooks.cjs'
        runner.write_bytes((Path(__file__).resolve().parents[1] / 'templates/guests/run-setup-hooks.cjs.tpl').read_bytes())
        name, interpreter, source = ('setup.ps1', 'powershell', 'Start-Sleep -Seconds 20') if os.name == 'nt' else ('setup.sh', 'bash', 'sleep 20')
        (self.root / name).write_text(source)
        (self.root / 'setup-hooks.json').write_text(json.dumps([{'script': name, 'interpreter': interpreter,
            'arguments': [], 'timeout_seconds': 1}]))
        result = subprocess.run(['node', str(runner)], capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('timed out', result.stderr)

    def test_guest_source_changes_invalidate_initialized_environment_fingerprint(self):
        script = self.root / 'runtime.sh'; script.write_text('echo first\n')
        requirements = self.root / 'requirements.json'
        requirements.write_text(json.dumps({'version': 1, 'desktop': {}, 'platforms': {'Linux': {
            'java': 21, 'appium': {'version': '3.2.2', 'drivers': {}, 'plugins': {}},
            'hooks': {'guest_setup': [{'script': 'runtime.sh', 'interpreter': 'bash',
                'arguments': ['one two'], 'timeout_seconds': 30}]}}}}))
        first = load(requirements, 'ubuntu')['sha256']
        script.write_text('echo second\n')
        self.assertNotEqual(load(requirements, 'ubuntu')['sha256'], first)

    def test_moving_content_between_scripts_changes_fingerprint(self):
        first = self.root / 'first.sh'; second = self.root / 'second.sh'
        first.write_text('echo "$1"\n'); second.write_text('')
        requirements = self.root / 'requirements.json'
        requirements.write_text(json.dumps({'version': 1, 'desktop': {}, 'platforms': {'Linux': {
            'java': 21, 'appium': {'version': '3.2.2', 'drivers': {}, 'plugins': {}},
            'hooks': {'guest_setup': [{'script': name, 'interpreter': 'bash',
                'arguments': [argument], 'timeout_seconds': 30}
                for name, argument in [('first.sh', 'first'), ('second.sh', 'second')]]}}}}))
        before = load(requirements, 'ubuntu')['sha256']
        first.write_text(''); second.write_text('echo "$1"\n')
        self.assertNotEqual(load(requirements, 'ubuntu')['sha256'], before)

    def test_script_fingerprint_does_not_depend_on_checkout_location(self):
        data = {'version': 1, 'desktop': {}, 'platforms': {'Linux': {
            'java': 21, 'appium': {'version': '3.2.2', 'drivers': {}, 'plugins': {}},
            'hooks': {'guest_setup': [{'script': 'setup.sh', 'interpreter': 'bash',
                'arguments': [], 'timeout_seconds': 30}]}}}}
        fingerprints = []
        for name in ['checkout-one', 'checkout-two']:
            root = self.root / name; root.mkdir()
            (root / 'setup.sh').write_text('echo fixture\n')
            path = root / 'requirements.json'; path.write_text(json.dumps(data))
            fingerprints.append(load(path, 'ubuntu')['sha256'])
        self.assertEqual(*fingerprints)

    def test_guest_runner_preserves_script_arguments_and_hides_output_on_failure(self):
        import os
        runner = self.root / 'run-setup-hooks.cjs'
        runner.write_bytes((Path(__file__).resolve().parents[1] / 'templates/guests/run-setup-hooks.cjs.tpl').read_bytes())
        if os.name == 'nt':
            source = 'param([string]$Value) if ($Value -ne "one two") { exit 2 }; Write-Output "private fixture"; exit 23'
            name, interpreter = 'setup.ps1', 'powershell'
        else:
            source = 'test "$1" = "one two" || exit 2\necho "private fixture"\nexit 23\n'
            name, interpreter = 'setup.sh', 'bash'
        (self.root / name).write_text(source)
        manifest = [{'script': name, 'interpreter': interpreter, 'arguments': ['one two'], 'timeout_seconds': 15}]
        (self.root / 'setup-hooks.json').write_text(json.dumps(manifest))
        result = subprocess.run(['node', str(runner)], capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('private setup-logs', result.stderr)
        self.assertNotIn('private fixture', result.stdout + result.stderr)
        self.assertIn('private fixture', (self.root / 'setup-logs/guest-setup-0.log').read_text())

    def test_guest_hook_inherits_standard_prebuilt_runtime_environment(self):
        import os
        runner = self.root / 'run-setup-hooks.cjs'
        runner.write_bytes((Path(__file__).resolve().parents[1] / 'templates/guests/run-setup-hooks.cjs.tpl').read_bytes())
        (self.root / 'appium').mkdir()
        (self.root / 'appium/runtime.json').write_text(json.dumps({'environment': {'RUNTIME_FIXTURE_DIR': '${RUNTIME}/assets/runtime'}}))
        name, interpreter, source = ('setup.ps1', 'powershell', 'Write-Output $env:RUNTIME_FIXTURE_DIR') if os.name == 'nt' else ('setup.sh', 'bash', 'printf "%s" "$RUNTIME_FIXTURE_DIR"')
        (self.root / name).write_text(source)
        (self.root / 'setup-hooks.json').write_text(json.dumps([{'script': name, 'interpreter': interpreter, 'arguments': [], 'timeout_seconds': 15}]))
        result = subprocess.run(['node', str(runner)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = (self.root / 'setup-logs/guest-setup-0.log').read_text().replace('\\', '/')
        self.assertIn(self.root.as_posix() + '/appium/assets/runtime', text)


if __name__ == '__main__':
    unittest.main()
