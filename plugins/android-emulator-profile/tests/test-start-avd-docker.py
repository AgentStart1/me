"""Fake SDK tools behind the real create/start/profile Shell boundaries."""
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tests'))
from shell_test_support import ShellTestCase

CONFIG = ('hw.gpu.enabled=no\nhw.gpu.mode=auto\nhw.accelerometer_uncalibrated=yes\n'
          'disk.dataPartition.size=2G\nduplicate.key=old-first\nduplicate.key=old-second\n')
PROFILE = '''AVD_NAME=docker-test-avd
SYS_IMG_PKG='system-images;android-36.1;google_apis'
EMULATOR_DISPLAY=:42
EMULATOR_FLAG_no_audio=true
EMULATOR_FLAG_no_snapshot=true
EMULATOR_FLAG_verbose=false
EMULATOR_FLAG_Mixed_Case=true
EMULATOR_VALUE_gpu=swiftshader_indirect
EMULATOR_VALUE_memory=2048
EMULATOR_VALUE_Custom_Value=preserved
EMULATOR_CONFIG_hw__gpu__enabled=yes
EMULATOR_CONFIG_hw__gpu__mode=swiftshader_indirect
EMULATOR_CONFIG_hw__accelerometer_uncalibrated=no
EMULATOR_CONFIG_disk__dataPartition__size=10G
EMULATOR_CONFIG_duplicate__key=final
'''
AVD = 'avds/docker-test-avd.avd/'
START = 'exec bash "$REPOSITORY/plugins/android-emulator-profile/scripts/start-avd.sh" "$FIXTURE/test.profile"'


class AvdShellTests(ShellTestCase):
    def setUp(self):
        super().setUp()
        fixtures = Path(__file__).parent / 'fixtures/start-avd-docker'
        for name, directory in [('emulator', 'emulator'), ('adb', 'platform-tools'),
                                ('sdkmanager', 'cmdline-tools/latest/bin'), ('avdmanager', 'cmdline-tools/latest/bin')]:
            self.write(f'sdk/{directory}/{name}', (fixtures / name).read_text(), True)
        self.write(AVD + 'config.ini', CONFIG)
        self.write(AVD + 'userdata-qemu.img', 'existing-data')
        self.write('avds/unrelated.avd/running.lock', '')
        self.profile = (f'ANDROID_HOME={self.path(self.root / "sdk")}\n'
                        f'ANDROID_AVD_HOME={self.path(self.root / "avds")}\n' + PROFILE)
        self.write('test.profile', self.profile)
        self.env.update(HOME=self.path(self.root / 'home'), USERPROFILE=str(self.root / 'home'))
        for key, name in [('EMULATOR_ARGS_LOG', 'args'), ('EMULATOR_ENV_LOG', 'env'),
                          ('EMULATOR_CONFIG_LOG', 'config'), ('ADB_ARGS_LOG', 'adb'),
                          ('AVDMANAGER_ARGS_LOG', 'create-args'), ('FAKE_EMULATOR_PID', 'held.pid')]:
            self.env[key] = self.path(self.root / name)

    def allow_wipe(self):
        self.write('test.profile', self.profile + 'EMULATOR_ALLOW_DATA_WIPE=true\n')

    def test_profile_shell_bridge_keeps_literals_out_of_environment(self):
        self.write('literal.profile', f'TEST_LITERAL=value; touch {self.path(self.root / "unexpected")}\n')
        result = self.run_shell('''source "$REPOSITORY/plugins/android-emulator-profile/scripts/profile-utils.sh"
load_profile "$FIXTURE/literal.profile"
printf '%s\n' "${TEST_LITERAL-unset}" "${PROFILE_VALUES[TEST_LITERAL]}"''')
        self.assertEqual(result.stdout.splitlines(), ['unset', self.read('literal.profile').strip().split('=', 1)[1]])
        self.assert_missing('unexpected')

    def test_profile_argument_bridge_preserves_case(self):
        result = self.run_shell('''source "$REPOSITORY/plugins/android-emulator-profile/scripts/profile-utils.sh"
declare -A PROFILE_VALUES=([EMULATOR_FLAG_Mixed_Case]=true [EMULATOR_VALUE_Custom_Value]=preserved [AVDMANAGER_FLAG_verbose]=true [AVDMANAGER_VALUE_Custom_Path]='relative avd')
emulator_args=(); avdmanager_args=()
append_args_from_profile emulator_args EMULATOR -
append_args_from_profile avdmanager_args AVDMANAGER --
printf '%s\n' "${emulator_args[@]}" "${avdmanager_args[@]}"''')
        self.assertEqual(result.stdout.splitlines(), ['-Mixed-Case', '-Custom-Value', 'preserved', '--verbose', '--Custom-Path', 'relative avd'])

    def test_existing_lock_refuses_start_without_mutating_config(self):
        self.write(AVD + 'stale.lock', '')
        result = self.run_shell(START, status=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Existing AVD lock', result.stderr)
        self.assertEqual(self.read(AVD + 'config.ini'), CONFIG)
        self.assertTrue((self.root / AVD / 'stale.lock').exists())

    def test_unapproved_wipe_refuses_start_without_mutating_config(self):
        result = self.run_shell(START, status=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('EMULATOR_ALLOW_DATA_WIPE', result.stderr)
        self.assertEqual(self.read(AVD + 'config.ini'), CONFIG)
        self.assert_missing('args')

    def test_create_matches_exact_avd_name(self):
        for listed in ('docker-test-avd', 'docker-test-avd-extra'):
            with self.subTest(listed=listed):
                (self.root / 'create-args').unlink(missing_ok=True)
                result = self.run_shell('bash "$REPOSITORY/plugins/android-emulator-profile/scripts/create-avd.sh" "$FIXTURE/test.profile"',
                                        env={'LISTED_AVD_NAME': listed})
                if listed == 'docker-test-avd':
                    self.assertIn("AVD 'docker-test-avd' already exists.", result.stderr)
                    self.assert_missing('create-args')
                else:
                    self.assertIn('create', self.read('create-args').splitlines())

    def test_approved_resize_applies_config_and_only_wipes_once(self):
        self.allow_wipe()
        result = self.run_shell(START)
        self.assertIn('Starting emulator...', result.stdout)
        self.assertIn('Emulator process has exited.', result.stdout)
        args = self.read('args').splitlines()
        for value in ('-avd', 'docker-test-avd', '-wipe-data', '-no-audio', '-no-snapshot',
                      '-gpu', 'swiftshader_indirect', '-memory', '2048', '-Mixed-Case', '-Custom-Value', 'preserved'):
            self.assertIn(value, args)
        self.assertNotIn('-verbose', args)
        self.assertEqual(self.read('env').strip(), 'DISPLAY=:42')
        config = self.read('config').splitlines()
        for value in ('hw.gpu.enabled=yes', 'hw.gpu.mode=swiftshader_indirect',
                      'hw.accelerometer_uncalibrated=no', 'disk.dataPartition.size=10G', 'duplicate.key=final'):
            self.assertIn(value, config)
        self.assertEqual(sum(line.startswith('duplicate.key=') for line in config), 1)
        self.assertTrue((self.root / 'avds/unrelated.avd/running.lock').exists())
        self.assert_missing(AVD + 'config.ini.profile-start.guard')
        self.assert_missing('adb')
        self.run_shell(START)
        self.assertNotIn('-wipe-data', self.read('args').splitlines())

    def test_first_boot_can_resize_without_wipe_permission(self):
        (self.root / AVD / 'userdata-qemu.img').unlink()
        self.run_shell(START)
        self.assertNotIn('-wipe-data', self.read('args').splitlines())
        self.assertIn('disk.dataPartition.size=10G', self.read('config'))

    @unittest.skipIf(os.name == 'nt', 'native Windows Ctrl+Break is covered by test-profile-controller.py')
    def test_competing_start_is_refused_and_cancellation_joins_emulator(self):
        self.allow_wipe()
        process = self.start_shell(START, env={'FAKE_EMULATOR_HOLD': '1'})
        self.wait_until(lambda: (self.root / 'held.pid').exists())
        result = self.run_shell(START, status=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('guard is busy', result.stderr)
        self.signal_shell()
        self.assertEqual(process.wait(timeout=15), 143)
        self.assert_missing(AVD + 'config.ini.profile-start.guard')
        self.assertNotEqual(self.run_shell('kill -0 "$(cat "$FIXTURE/held.pid")"', status=None).returncode, 0)
        self.assert_missing('adb')


if __name__ == '__main__':
    unittest.main()
