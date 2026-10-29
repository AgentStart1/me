"""Both public build launchers: argument validation and real dispatch."""
import unittest
from shell_test_support import ROOT, ShellTestCase


class BuildCliTests(ShellTestCase):
    def command(self, client, *args, status=0):
        return self.run_shell('bash "$REPOSITORY/scripts/build-$1-plugin-package.sh" "${@:2}"', client, *args, status=status)

    def test_help(self):
        for client in ('claude', 'codex'):
            for option in ('--help', '-h'):
                with self.subTest(client=client, option=option):
                    self.assertIn('--all [--output-dir directory]', self.command(client, option).stdout)

    def test_invalid_arguments(self):
        for client in ('claude', 'codex'):
            for args in ((), ('--unknown',), ('--output-dir', str(self.root / 'output')),
                         ('--all', '--unknown'), ('--all', '--output-dir')):
                with self.subTest(client=client, args=args):
                    self.assertNotEqual(self.command(client, *args, status=None).returncode, 0)

    def test_default_dispatch(self):
        self.mock('python3', 'printf "%s\\n" "$@" > "$FIXTURE/arguments"')
        for client in ('claude', 'codex'):
            with self.subTest(client=client):
                self.command(client, '--all')
                self.assertEqual(self.read('arguments').splitlines(),
                                 [self.path(ROOT) + '/scripts/build-plugin-packages.py', '--client', client])

    def test_explicit_output_directory(self):
        for client in ('claude', 'codex'):
            with self.subTest(client=client):
                self.command(client, '--all', '--output-dir', self.path(self.root / ('me.' + client)))
                self.assertTrue((self.root / ('me.' + client) / 'README.md').is_file())


if __name__ == '__main__':
    unittest.main()
