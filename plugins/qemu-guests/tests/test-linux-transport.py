"""Cross-platform JVM staging and WebDriver handoff contracts."""
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from test_linux_transport import LinuxTransport
from test_appium_proxy import AppiumProxy, Creation, RelayState
from test_java_launch import arguments


class LinuxTransportTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name).resolve()
        self.native = self.root / 'native linux.jar'
        self.native.write_bytes(b'prebuilt')
        runtime = self.root / 'runtime.json'
        runtime.write_text(json.dumps({'root': '/home/test/runtime', 'java': '/jdk/bin/java',
                                      'classpath': [str(self.native)]}))
        self.runtime = runtime
        self.transport = LinuxTransport({'ssh_user': 'test', 'access_key': 'fixture', 'ssh_port': 2222},
                                        self.root, runtime)

    def test_jvm_paths_and_classpath_are_mapped_without_changing_service_urls(self):
        args = self.root / 'launch with spaces.args'
        session = self.root / 'private/session.json'
        cp = self.root / 'app.jar'
        commands = []
        self.transport.shell = lambda script, data=None: commands.append((script, data))
        caps = self.transport.upload_arguments(args,
            ['-Dsession=' + str(session), '-Dservice=http://127.0.0.1:20001',
             '-XX:ErrorFile=' + str(self.root / 'hs_err%p.log'), '-cp', str(cp), 'Main', 'space argument'],
            {'inputs': ['session'], 'outputs': [], 'directories': []}, {'appium:app': 'java.exe'})
        values = [json.loads(line) for line in commands[0][1].decode().splitlines()]
        self.assertEqual(values[0], '-Dsession=' + self.transport.mapped(session))
        self.assertEqual(values[1], '-Dservice=http://127.0.0.1:20001')
        self.assertEqual(values[2], '-XX:ErrorFile=' + self.transport.mapped(self.root / 'hs_err%p.log'))
        self.assertEqual(values[4], self.transport.mapped(cp) + ':' + self.transport.mapped(self.native))
        self.assertEqual(values[-1], 'space argument')
        self.assertEqual(caps['appium:app'], '/jdk/bin/java')
        self.assertEqual(caps['appium:appArguments'], ['@' + self.transport.mapped(args)])

    def test_java_argument_array_is_read_without_shell_evaluation(self):
        path = self.root / 'launch.args'
        path.write_text('"Main"\n')
        self.assertEqual(arguments({'appium:appArguments': ['@' + str(path)]}), (path, ['Main']))
        with self.assertRaisesRegex(ValueError, 'one JVM'):
            arguments({'appium:appArguments': ['@' + str(path), 'unexpected']})

    def test_archive_contains_only_mapped_prebuilt_regular_files(self):
        captured = []
        self.transport.shell = lambda script, data=None: captured.append((script, data))
        self.transport.stage([self.native])
        import io
        with tarfile.open(fileobj=io.BytesIO(captured[-1][1]), mode='r:gz') as archive:
            names = archive.getnames()
            self.assertEqual(len(names), 1)
            self.assertFalse(names[0].startswith('/'))
            self.assertNotIn('..', names[0].split('/'))
            self.assertEqual(archive.extractfile(names[0]).read(), b'prebuilt')
        self.assertFalse((self.root / 'runtime.tar.gz').exists())

    def test_runtime_archive_rejects_credentials(self):
        secret = self.root / 'access.key'; secret.write_text('fixture')
        with self.assertRaisesRegex(ValueError, 'credential'):
            self.transport.stage([secret])

    def test_private_cleanup_refuses_parent_or_unrelated_directory(self):
        private = self.root / 'private'
        self.transport.shell = Mock()
        for path in (private, self.root, self.root / 'unrelated'):
            with self.assertRaisesRegex(ValueError, 'outside'):
                self.transport.remove_private_directory(path, [private])
        self.transport.shell.assert_not_called()

    def test_private_cleanup_maps_only_the_requested_case(self):
        private = self.root / 'private'
        self.transport.shell = Mock()
        self.transport.remove_private_directory(private / 'case', [private])
        command = self.transport.shell.call_args.args[0]
        self.assertIn(self.transport.mapped(private / 'case'), command)

    def test_missing_prebuilt_runtime_fails_without_running_guest_commands(self):
        config = json.loads(self.runtime.read_text()); config['classpath'] = [str(self.root / 'missing.jar')]
        self.runtime.write_text(json.dumps(config))
        with self.assertRaisesRegex(ValueError, 'prebuilt'):
            LinuxTransport({'ssh_user': 'test', 'access_key': 'fixture', 'ssh_port': 2222}, self.root, self.runtime)

    def test_initialized_guest_supplies_prebuilt_classpath_without_operator_override(self):
        with patch.object(LinuxTransport, 'shell', return_value=b'{"example:native:1.0":"assets/native.jar"}'):
            transport = LinuxTransport({'ssh_user': 'test', 'access_key': 'fixture', 'ssh_port': 2222}, self.root)
        self.assertEqual(transport.java, '/usr/bin/java')
        self.assertEqual(transport.classpath, [])
        self.assertEqual(transport.guest_classpath, ['/opt/qemu-guests/appium/assets/native.jar'])

    def test_initialized_guest_cannot_escape_its_bundled_native_asset_directory(self):
        with patch.object(LinuxTransport, 'shell', return_value=b'{"example:native:1.0":"../outside.jar"}'):
            with self.assertRaisesRegex(ValueError, 'unsafe classpath'):
                LinuxTransport({'ssh_user': 'test', 'access_key': 'fixture', 'ssh_port': 2222}, self.root)

    def test_shallow_runtime_root_is_rejected(self):
        config = json.loads(self.runtime.read_text()); config['root'] = '/home'
        self.runtime.write_text(json.dumps(config))
        with self.assertRaisesRegex(ValueError, 'dedicated'):
            LinuxTransport({'ssh_user': 'test', 'access_key': 'fixture', 'ssh_port': 2222}, self.root, self.runtime)

    def test_webdriver_receives_transformed_capabilities(self):
        proxy = AppiumProxy.__new__(AppiumProxy)
        proxy.sessions = set(); proxy.launch = Mock(); proxy.request = Mock()
        proxy.creation = Creation.IDLE
        proxy.relay_state = RelayState.OPEN
        proxy.launch.prepare.return_value = {'appium:app': '/jdk/bin/java', 'appium:appArguments': ['@/runtime/app.args']}
        proxy.request.return_value = (200, {}, b'{"value":{"sessionId":"owned"}}')
        proxy.relay('POST', '/session', b'{"capabilities":{"alwaysMatch":{"appium:app":"java.exe"}}}')
        forwarded = json.loads(proxy.request.call_args.args[2])['capabilities']['alwaysMatch']
        self.assertEqual(forwarded, proxy.launch.prepare.return_value)
        self.assertEqual(proxy.sessions, {'owned'})


if __name__ == '__main__':
    unittest.main()
