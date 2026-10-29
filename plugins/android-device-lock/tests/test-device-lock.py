"""Real lease CLI and remote templates against a private fake adb filesystem."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tests'))
from shell_test_support import ShellTestCase

RECORD = dict(project_dir='/fixture', test_name='expired-fixture',
              requested_at_utc='1970-01-01T00:00:00Z', acquired_at_utc='1970-01-01T00:00:00Z',
              max_timeout_seconds=1, expires_at_epoch=1, host='fixture-host', pid=1,
              owner_token='expired-private-token')
ENTRY = 'bash "$REPOSITORY/plugins/android-device-lock/scripts/adb-device-lock.sh"'
OPTIONS = '--serial fake-device --lock-path /data/local/tmp/test.lock.d --wait-timeout-seconds 0 --poll-seconds 1'


class DeviceLeaseTests(ShellTestCase):
    def setUp(self):
        super().setUp()
        self.install_mocks(Path(__file__).parent / 'fixtures/device-lock')
        (self.root / 'device').mkdir()
        self.env['FAKE_DEVICE_ROOT'] = self.path(self.root / 'device')
        self.lease = self.root / 'device/test.lock.d'

    def command(self, action, token='owner.token', extra='', env=None, status=0):
        return self.run_shell(f'{ENTRY} {action} {OPTIONS} --token-file "$FIXTURE/{token}" {extra}',
                              env=env, status=status)

    def assert_released(self, token='owner.token'):
        for name in ('device/test.lock.d', 'device/test.lock.d.guard', token):
            self.assert_missing(name)

    def test_invalid_lock_paths(self):
        for path in ('/data/local/tmp/', '/data/local/tmp/../other', '/data/local/tmp/./other', '/'):
            with self.subTest(path=path):
                result = self.run_shell(f'{ENTRY} acquire --lock-path "$1" --wait-timeout-seconds 0', path, status=None)
                self.assertNotEqual(result.returncode, 0)

    def test_expired_lease_race_has_one_owner_and_hides_tokens(self):
        self.write('device/test.lock.d/lock.json', json.dumps(RECORD))
        # Both real CLI processes contend on the same fake remote filesystem.
        self.run_shell(f'''{ENTRY} acquire {OPTIONS} --token-file "$FIXTURE/a.token" > "$FIXTURE/a.log" 2>&1 &
a=$!
{ENTRY} acquire {OPTIONS} --token-file "$FIXTURE/b.token" > "$FIXTURE/b.log" 2>&1 &
b=$!
a_status=0; wait "$a" || a_status=$?
b_status=0; wait "$b" || b_status=$?
printf '%s %s' "$a_status" "$b_status" > "$FIXTURE/status"''')
        self.assertIn(self.read('status'), ('0 1', '1 0'))
        token = 'a.token' if self.read('status').startswith('0') else 'b.token'
        self.assertIn(self.read(token).strip(), self.read('device/test.lock.d/lock.json'))
        for name in ('a.log', 'b.log'):
            self.assertNotIn('owner_token', self.read(name))
        self.command('release', token)
        self.assert_released(token)

    def test_wrong_owner_cannot_release_and_owner_can_renew(self):
        self.command('acquire')
        self.write('wrong.token', 'wrong-owner')
        self.assertNotEqual(self.command('release', 'wrong.token', status=None).returncode, 0)
        self.assertIn(self.read('owner.token').strip(), self.read('device/test.lock.d/lock.json'))
        self.command('renew')
        self.command('release')
        self.assert_released()

    def test_failed_publication_removes_lease_and_guard(self):
        self.assertNotEqual(self.command('acquire', env={'FAIL_PUSH': '1'}, status=None).returncode, 0)
        self.assert_released()

    def test_existing_guard_is_preserved(self):
        (self.root / 'device/test.lock.d.guard').mkdir()
        self.assertNotEqual(self.command('acquire', status=None).returncode, 0)
        self.assertTrue((self.root / 'device/test.lock.d.guard').is_dir())
        self.assertFalse(self.lease.exists())

    def test_invalid_metadata_is_preserved_without_disclosure(self):
        records = {
            'corrupt': '{"expires_at_epoch":1,"owner_token":"must-stay-private", broken}',
            'boolean': json.dumps(RECORD | {'expires_at_epoch': True}),
            'missing': json.dumps({key: value for key, value in RECORD.items() if key != 'host'}),
            'duplicate': json.dumps(RECORD)[:-1] + ',"expires_at_epoch":1}',
            'nonfinite': json.dumps(RECORD | {'extra': float('nan')}),
        }
        for name, content in records.items():
            with self.subTest(kind=name):
                self.write('device/test.lock.d/lock.json', content)
                result = self.command('acquire', status=None)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.read('device/test.lock.d/lock.json'), content)
                self.assertNotIn('must-stay-private', result.stdout + result.stderr)
                self.assertNotIn(RECORD['owner_token'], result.stdout + result.stderr)

    def test_control_characters_roundtrip_through_renewal(self):
        name = 'quoted "name"\nnext line ${owner_token}\n'
        self.run_shell(f'{ENTRY} acquire {OPTIONS} --token-file "$FIXTURE/owner.token" --test-name "$1"', name)
        self.command('renew')
        record = json.loads(self.read('device/test.lock.d/lock.json'))
        self.assertEqual(record['test_name'], name)
        self.assertIs(type(record['expires_at_epoch']), int)
        self.command('release')
        self.assert_released()

    def test_run_preserves_child_failure_and_cleans_lease(self):
        # Native Windows process creation can resolve bare bash to the WSL launcher.
        self.command('run', extra="-- \"$BASH\" -c 'exit 23'", status=23)
        self.assert_released()

    def test_failed_remote_cleanup_keeps_recovery_token(self):
        for mode, child_status in (('release', 0), ('run', 0), ('run', 23)):
            with self.subTest(mode=mode, child_status=child_status):
                before = None
                if mode == 'release':
                    self.command('acquire')
                    before = self.read('owner.token')
                result = self.command(mode, extra=f"-- \"$BASH\" -c 'exit {child_status}'" if mode == 'run' else '',
                                      env={'FAIL_REMOTE_RM': '1'}, status=None)
                self.assertNotEqual(result.returncode, 0)
                if child_status:
                    self.assertEqual(result.returncode, child_status)
                token = self.read('owner.token')
                self.assertTrue(token.strip())
                if before is not None:
                    self.assertEqual(token, before)
                self.assertIn(token.strip(), self.read('device/test.lock.d/lock.json'))
                self.assert_missing('device/test.lock.d.guard')
                self.assertNotIn('Released Android device lock', result.stdout + result.stderr)
                self.command('release')
                self.assert_released()


if __name__ == '__main__':
    unittest.main()
