"""Transparent environment roles, host command ownership and WebDriver relay contracts."""
import base64
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from test_appium_proxy import AppiumProxy, CleanupUncertain
from test_environment import guest_lease, run
from test_environment_config import load
from test_java_launch import JavaLaunch, properties, service_ports
from test_guest_transport import GuestTransport


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def test_large_unicode_guest_scripts_are_data_not_remote_command_arguments(self):
        transport = GuestTransport({'os': 'windows', 'ssh_user': 'developer',
                                    'ssh_port': 2222, 'access_key': 'fixture-key'}, self.root)
        script = "Write-Output '" + '\u03bb' * 20000 + "'"
        with patch('test_guest_transport.subprocess.run', return_value=subprocess.CompletedProcess([], 0, b'OK', b'')) as run:
            self.assertEqual(transport.powershell(script), b'OK')
        args, kwargs = run.call_args
        self.assertLess(len(args[0][-1]), 2000)
        self.assertEqual(args[0][-1], 'powershell.exe -NoProfile -NonInteractive -Command -')
        self.assertTrue(kwargs['input'].endswith(b'\n'))
        self.assertIn(base64.b64encode(script.encode('utf-8')), kwargs['input'])

    def test_guest_script_errors_keep_private_diagnostics_and_fail_the_operation(self):
        private = self.root / 'session'
        private.mkdir()
        transport = GuestTransport({'os': 'windows', 'ssh_user': 'developer',
                                    'ssh_port': 2222, 'access_key': 'fixture-key'}, private)
        with patch('test_guest_transport.subprocess.run', return_value=subprocess.CompletedProcess([], 1, b'', b'fixture-error')):
            with self.assertRaisesRegex(RuntimeError, 'SSH command failed'):
                transport.powershell("throw 'fixture-error'")
        self.assertEqual((self.root / 'transport-error.log').read_bytes(), b'fixture-error')

    def test_configuration_rejects_cleanup_of_the_workspace(self):
        path = self.root / 'environment.json'
        path.write_text(json.dumps({'version': 1, 'appium': {'guest': 'guest.json', 'cleanup_roots': ['.'],
            'launch': {'kind': 'java-argfile', 'inputs': [], 'outputs': [], 'directories': [], 'services': []}}}))
        with self.assertRaisesRegex(ValueError, 'strictly inside'):
            load(path)

    def test_unresolved_environment_paths_fail_before_starting_commands(self):
        path = self.root / 'environment.json'
        path.write_text('{"version":1,"docker":{"profile":"${UNSET_TEST_ENV_PROFILE}"}}')
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'unset'):
                load(path)

    def test_operator_connections_stay_outside_project_configuration(self):
        path = self.root / 'environment.json'
        path.write_text(json.dumps({'version': 1, 'appium': {'cleanup_roots': ['private'],
            'launch': {'kind': 'java-argfile', 'inputs': [], 'outputs': [], 'directories': [],
                       'services': [], 'artifacts': ['diagnostic.agent']}}}))
        with patch.dict(os.environ, {'TEST_ENV_DOCKER_PROFILE': str(self.root / 'backend.profile'),
                                     'TEST_ENV_GUEST_PROFILE': str(self.root / 'guest.json')}):
            config = load(path)
        self.assertEqual(config['docker'], self.root / 'backend.profile')
        self.assertEqual(config['appium']['guest'], self.root / 'guest.json')
        self.assertEqual(config['appium']['launch']['artifacts'], ['diagnostic.agent'])

    def test_host_command_arguments_and_exit_code_are_preserved_without_services(self):
        code = "import os,sys; assert os.environ['ENV_FIXTURE']=='value'; assert sys.argv[1]=='one two'; sys.exit(23)"
        result = run({'workspace': self.root, 'environment': {'ENV_FIXTURE': 'value'}},
                     [sys.executable, '-c', code, 'one two'])
        self.assertEqual(result, 23)

    def test_service_roles_forward_only_loopback_urls_and_deduplicate_ports(self):
        props = properties(['-Dtest.http=http://127.0.0.1:20001', '-Dtest.ws=ws://localhost:20001',
                            '-Dtest.external=https://example.invalid:443'])
        self.assertEqual(service_ports(props, list(props)), [20001])

    def test_prebuilt_diagnostic_artifact_is_staged_at_session_creation(self):
        agent = self.root / 'diagnostic.jar'
        agent.write_bytes(b'prebuilt fixture')
        argument_file = self.root / 'launch.args'
        argument_file.write_text(json.dumps('-Ddiagnostic.agent=' + str(agent)) + '\n')
        staged = []

        class Transport:
            def mkdir(self, paths): pass
            def stage(self, paths): staged.extend(paths)
            def upload(self, path): pass

        config = {'cleanup_roots': [], 'launch': {'inputs': [], 'outputs': [], 'directories': [],
                                                'services': [], 'artifacts': ['diagnostic.agent']}}
        launch = JavaLaunch(Transport(), config, self.root)
        with patch('test_java_launch.artifact_files', return_value=[]):
            launch.prepare({'appium:appArguments': '@' + str(argument_file)})
        self.assertEqual(staged, [agent])

    def test_guest_test_lease_cannot_be_stolen_and_is_released(self):
        with guest_lease(self.root):
            with self.assertRaises(FileExistsError):
                with guest_lease(self.root):
                    self.fail('Existing lease was acquired twice')
        self.assertFalse((self.root / 'test-environment.lock').exists())

    def test_uncertain_cleanup_retains_the_guest_test_lease(self):
        with self.assertRaises(CleanupUncertain):
            with guest_lease(self.root):
                raise CleanupUncertain('fixture shutdown failure')
        record = json.loads((self.root / 'test-environment.lock/owner.json').read_text())
        self.assertEqual(record['phase'], 'cleanup-uncertain')

    def test_restarts_retain_guest_private_state_until_the_host_run_finishes(self):
        root = self.root / 'private'
        folder = root / 'case'; folder.mkdir(parents=True)
        incoming = folder / 'session.json'
        incoming.write_text('temporary injected session')
        arguments = self.root / 'launch.args'
        arguments.write_text(json.dumps('-Dtest.session=' + str(incoming)) + '\n')

        class Transport:
            def __init__(self): self.deleted = []; self.cleaned = []; self.uploads = []
            def mkdir(self, paths): pass
            def stage(self, paths): pass
            def upload(self, path): self.uploads.append(path)
            def remove_files(self, paths): self.deleted.extend(paths)
            def remove_private_directory(self, path, roots): self.cleaned.append(path)

        transport = Transport()
        config = {'cleanup_roots': [root], 'launch': {'inputs': ['test.session'], 'outputs': [], 'directories': [], 'services': []}}
        launch = JavaLaunch(transport, config, self.root)
        caps = {'appium:appArguments': '"@' + str(arguments) + '"', 'appium:app': 'javaw.exe'}
        with patch('test_java_launch.artifact_files', return_value=[]):
            launch.prepare(caps)
            incoming.unlink()  # The original client requests restart without injected credentials.
            launch.prepare(caps)
        self.assertEqual(transport.deleted, [incoming])
        self.assertEqual(transport.cleaned, [])
        launch.close()
        self.assertEqual(transport.cleaned, [folder])

    def test_remote_outputs_cannot_overwrite_files_outside_the_host_workspace(self):
        arguments = self.root / 'launch.args'
        arguments.write_text(json.dumps('-Dtest.output=' + str(self.root.parent / 'outside.log')) + '\n')
        config = {'cleanup_roots': [self.root / 'private'], 'launch': {
            'inputs': [], 'outputs': ['test.output'], 'directories': [], 'services': []}}
        launch = JavaLaunch(None, config, self.root)
        with self.assertRaisesRegex(ValueError, 'inside the host test workspace'):
            launch.prepare({'appium:appArguments': '@' + str(arguments)})

    def test_webdriver_passthrough_preserves_nonlaunch_response_status_and_body(self):
        payload = b'{"value":{"ready":true,"build":{"version":"fixture"}}}'

        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.end_headers(); self.wfile.write(payload)

        server = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        proxy = AppiumProxy(f'http://127.0.0.1:{server.server_port}', None,
                            {'launch': {}, 'cleanup_roots': []}, self.root)
        proxy.start(); self.addCleanup(proxy.close)
        connection = http.client.HTTPConnection('127.0.0.1', proxy.server.server_port)
        self.addCleanup(connection.close)
        connection.request('GET', '/status')
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertEqual(response.read(), payload)


if __name__ == '__main__':
    unittest.main()
