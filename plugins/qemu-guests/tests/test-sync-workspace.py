"""Real archive/SSH orchestration with isolated state and fake remote IO."""
from pathlib import Path
import os
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tests'))
from shell_test_support import ShellTestCase


class SyncTests(ShellTestCase):
    def setUp(self):
        super().setUp()
        self.install_mocks(Path(__file__).parent / 'fixtures/sync-workspace')
        self.write('test.profile', 'VM_NAME=test-vm\nSSH_PORT=2299\n')
        self.write('home/id_ed25519', 'key\n')
        self.write('source/src/app.txt', 'included\n')
        for name in ('.env', '.git/config', 'coverage/report.txt'):
            self.write('source/' + name, 'excluded\n')
        self.env.update(QEMU_STATE_PYTHON=self.path(sys.executable),
                        QEMU_ALPINE_BASE_DIR=self.path(self.root / 'home'),
                        MOCK_SSH_LOG=self.path(self.root / 'ssh.log'),
                        MOCK_ARCHIVE_LOG=self.path(self.root / 'archive.log'))
        self.write('home/vms/test-vm.pid', str(os.getpid()))

    def sync(self, source='source', remote='/root/example'):
        return self.run_shell('bash "$REPOSITORY/plugins/qemu-guests/scripts/sync-workspace.sh" '
                              '--profile "$FIXTURE/test.profile" --remote-dir "$1" '
                              '--exclude coverage "$FIXTURE/$2"', remote, source, status=None)

    def test_transfer_stages_then_replaces_and_applies_exclusions(self):
        result = self.sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        log = self.read('ssh.log')
        stages = ["rm -rf '/root/example.new'", "tar -xf - -C '/root/example.new'",
                  "mv '/root/example.new' '/root/example'"]
        self.assertEqual(sorted(log.index(stage) for stage in stages), [log.index(stage) for stage in stages])
        self.assertIn('Workspace synced', result.stderr)
        archive = self.read('archive.log').splitlines()
        self.assertIn('./src/app.txt', archive)
        for prefix in ('./.env', './.git/', './coverage/'):
            self.assertFalse(any(name.startswith(prefix) for name in archive), archive)
        self.assert_missing('home/run/vm-operation.lock')

    def test_guest_root_is_rejected_before_transfer(self):
        result = self.sync(remote='/')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Refusing unsafe remote directory', result.stderr)
        self.assert_missing('ssh.log')

    def test_missing_source_is_rejected_before_transfer(self):
        self.assertNotEqual(self.sync(source='missing').returncode, 0)
        self.assert_missing('ssh.log')


if __name__ == '__main__':
    unittest.main()
