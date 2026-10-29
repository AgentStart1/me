"""Proxy build boundary: fake SSH, real archives and ownership controllers."""
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tests'))
from shell_test_support import ShellTestCase

BUILD = 'exec bash "$REPOSITORY/plugins/qemu-guests/scripts/build-docker-proxy.sh" --profile "$FIXTURE/test.profile"'


class ProxyBuildTests(ShellTestCase):
    def setUp(self):
        super().setUp()
        self.install_mocks(Path(__file__).parent / 'fixtures/build-docker-proxy')
        self.write('test.profile', 'VM_NAME=test-vm\nSSH_PORT=2299\n')
        self.write('home/vms/test-vm.pid', str(os.getpid()))
        (self.root / 'output').mkdir()
        (self.root / 'user').mkdir()
        self.env.update(QEMU_STATE_PYTHON=self.path(sys.executable),
                        HOME=self.path(self.root / 'user'), USERPROFILE=str(self.root / 'user'),
                        QEMU_ALPINE_BASE_DIR=self.path(self.root / 'home'),
                        QEMU_DOCKER_PROXY_DIR=self.path(self.root / 'output'),
                        PROXY_SSH_LOG=self.path(self.root / 'ssh.log'),
                        PROXY_ARCHIVE_LOG=self.path(self.root / 'archive.log'))
        self.name = 'docker.exe' if os.name == 'nt' else 'docker'
        self.lock = self.root / 'user/.cache/me/locks/build-docker-proxy.lock'

    def test_bootstrap_transfer_target_and_cleanup_without_host_go(self):
        self.run_shell(BUILD)
        self.assertEqual(self.read('output/' + self.name), 'proxy executable')
        target = 'windows' if os.name == 'nt' else 'linux'
        self.assertIn(f"'{target}' 'amd64'", self.read('ssh.log'))
        for name in ('./main.go', 'build-docker-proxy.sh.tpl'):
            self.assertIn(name, self.read('archive.log'))
        self.assert_remote_cleanup()

    def assert_remote_cleanup(self):
        self.assertIn("rm -rf -- '/tmp/qemu-docker-proxy.mock123'", self.read('ssh.log'))
        self.assertEqual(list((self.root / 'output').glob('.docker-proxy.*')), [])
        self.assertFalse(self.lock.exists())

    def test_cross_build_preserves_host_executable(self):
        self.write('output/' + self.name, 'existing-host')
        self.run_shell(BUILD + ' --target-os darwin --target-arch arm64')
        self.assertEqual(self.read('output/darwin-arm64/docker'), 'proxy executable')
        self.assertEqual(self.read('output/' + self.name), 'existing-host')
        self.assertIn("'darwin' 'arm64'", self.read('ssh.log'))

    def test_failures_preserve_existing_proxy_and_clean_staging(self):
        for failure in ('build', 'download'):
            with self.subTest(failure=failure):
                self.write('output/' + self.name, 'previous')
                self.write('ssh.log', '')
                result = self.run_shell(BUILD, env={'PROXY_FAIL': failure}, status=None)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.read('output/' + self.name), 'previous')
                self.assert_remote_cleanup()

    def test_builds_with_different_vm_and_output_directories_serialize(self):
        events = self.path(self.root / 'events')
        first = self.start_shell(BUILD, 'first', {'PROXY_EVENTS': events, 'PROXY_CALL': 'first'})
        self.wait_until(lambda: (self.root / 'events').exists())
        self.write('other-vm/vms/test-vm.pid', str(os.getpid()))
        second = self.start_shell(BUILD, 'second', dict(PROXY_EVENTS=events, PROXY_CALL='second',
                                  QEMU_ALPINE_BASE_DIR=self.path(self.root / 'other-vm'),
                                  QEMU_DOCKER_PROXY_DIR=self.path(self.root / 'other-output')))
        self.wait_until(lambda: 'Waiting for another Docker proxy build' in self.read('second.log'))
        self.write('release-first', '')
        self.assertEqual(first.wait(timeout=30), 0, self.read('first.log'))
        self.assertEqual(second.wait(timeout=30), 0, self.read('second.log'))
        self.assertEqual(self.read('events').splitlines(), ['start first', 'end first', 'start second', 'end second'])
        self.assertFalse(self.lock.exists())

    def test_default_output_is_shared_user_storage(self):
        self.run_shell('unset QEMU_DOCKER_PROXY_DIR\n' + BUILD)
        self.assertEqual(self.read('user/.local/share/me/docker-proxy/' + self.name), 'proxy executable')

    def hold_lock(self):
        holder = self.start_shell('while :; do sleep 0.1; done', 'holder')
        self.lock.mkdir(parents=True)
        token = self.read('holder.pid')
        (self.lock / 'owner.pid').write_text(token)
        return holder, token

    def test_timeout_preserves_active_lock(self):
        _, token = self.hold_lock()
        result = self.run_shell(BUILD, env={'QEMU_DOCKER_BUILD_LOCK_TIMEOUT': '1'}, status=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('timed out', result.stderr)
        self.assertEqual((self.lock / 'owner.pid').read_text(), token)

    def test_terminated_waiter_preserves_other_owner(self):
        _, token = self.hold_lock()
        waiter = self.start_shell(BUILD, 'waiter')
        self.wait_until(lambda: 'Waiting for another Docker proxy build' in self.read('waiter.log'))
        self.signal_shell('waiter')
        self.assertNotEqual(waiter.wait(timeout=15), 0)
        self.assertEqual((self.lock / 'owner.pid').read_text(), token)

    def test_stale_lock_requires_explicit_recovery(self):
        self.lock.mkdir(parents=True)
        (self.lock / 'owner.pid').write_text('999999999\n')
        result = self.run_shell(BUILD, status=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('stale proxy build lock', result.stderr)
        self.assertEqual((self.lock / 'owner.pid').read_text(), '999999999\n')


if __name__ == '__main__':
    unittest.main()
