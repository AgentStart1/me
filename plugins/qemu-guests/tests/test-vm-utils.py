"""Shell utility boundaries; native lifecycle/state algorithms have their own suites."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tests'))
from shell_test_support import ROOT, ShellTestCase

PLUGIN = ROOT / 'plugins/qemu-guests'
SOURCE = '''export QEMU_ALPINE_BASE_DIR="$FIXTURE/home"
source "$REPOSITORY/plugins/qemu-guests/scripts/vm-utils.sh"
VM_DIR="$FIXTURE/vms"
RUN_DIR="$FIXTURE/run"
ACTIVE_LOCK_DIR="$RUN_DIR/active-vm.lock"
STATE_GUARD_DIR="$RUN_DIR/vm-state.guard"
mkdir -p "$VM_DIR"
load_profile "$FIXTURE/test.profile"
'''
PROFILE = '''VM_NAME=test-vm
VM_MEMORY=1024
VM_CPUS=1
VM_DISK_SIZE=10G
SSH_PORT=2299
DOCKER_DAEMON_PORT=2375
TESTCONTAINERS_PORT_START=20000
TESTCONTAINERS_PORT_END=20002
PORT_FORWARD=9090:80
'''


class UtilityShellTests(ShellTestCase):
    def setUp(self):
        super().setUp()
        for source in (Path(__file__).parent / 'fixtures/vm-utils').iterdir():
            if source.suffix != '.json':
                self.write('bin/' + source.name, source.read_text(), True)
        self.write('test.profile', PROFILE)
        (self.root / 'home').mkdir()
        self.env.update(HOME=self.path(self.root / 'home'), USERPROFILE=str(self.root / 'home'))

    def shell(self, body, *args, **kwargs):
        return self.run_shell(SOURCE + body, *args, **kwargs)

    def test_template_replacement_is_literal(self):
        self.write('render.tpl', 'name={{NAME}}\nspecial={{SPECIAL}}\n')
        self.shell('render_template "$FIXTURE/render.tpl" "$FIXTURE/rendered" NAME "vm&one" SPECIAL \'a|b/c\\path\'')
        self.assertEqual(self.read('rendered'), 'name=vm&one\nspecial=a|b/c\\path\n')

    def test_failed_template_render_leaves_no_output(self):
        self.write('render.tpl', 'value={{VALUE}}\nmissing={{MISSING}}\n')
        self.assertNotEqual(self.shell('render_template "$FIXTURE/render.tpl" "$FIXTURE/rendered" VALUE ok', status=None).returncode, 0)
        self.assert_missing('rendered')

    def test_provisioning_templates_render_values(self):
        cases = [
            ('setup-alpine.answers.tpl', ['VM_NAME', 'test-vm', 'FALLBACK_MAIN', 'https://cdn.example/alpine/v3.24/main',
              'FALLBACK_COMMUNITY', 'https://cdn.example/alpine/v3.24/community', 'ROOT_SSH_KEY', 'ssh-ed25519 mock&key'],
             ['HOSTNAMEOPTS=test-vm', 'ROOTSSHKEY="ssh-ed25519 mock&key"']),
            ('testcontainers-ports.conf.tpl', ['TESTCONTAINERS_PORT_START', '20000', 'TESTCONTAINERS_PORT_END', '20255'],
             ['net.ipv4.ip_local_port_range = 20000 20255']),
            ('docker-daemon.json.tpl', ['DOCKER_GUEST_PORT', '2375', 'DOCKER_DNS_ADDRESS', '192.168.127.1'],
             ['tcp://0.0.0.0:2375', '"dns": ["192.168.127.1"]']),
            ('setup.start.tpl', ['ALPINE_FALLBACK_MIRROR', 'https://dl-cdn.alpinelinux.org/alpine'],
             ['ALPINE_FALLBACK_MIRROR="https://dl-cdn.alpinelinux.org/alpine"']),
        ]
        for name, args, expected in cases:
            with self.subTest(template=name):
                self.shell('render_template "$REPOSITORY/plugins/qemu-guests/templates/$1" "$FIXTURE/rendered" "${@:2}"', name, *args)
                for value in expected:
                    self.assertIn(value, self.read('rendered'))

    def test_platform_and_qemu_tool_resolution(self):
        result = self.shell('platform_tag\nresolve_qemu\nresolve_qemu_img "$(resolve_qemu)"')
        platform, qemu, image = result.stdout.splitlines()
        self.assertIn(platform, ('linux', 'mac', 'win', 'unknown'))
        self.assertIn('qemu-system-x86_64', qemu)
        self.assertIn('qemu-img', image)

    def test_profile_literal_values_and_crlf(self):
        for content, name, end in [(PROFILE, 'test-vm', '20002'), ('VM_NAME=crlf-vm\r\nVM_MEMORY=4096\r\n', 'crlf-vm', 'unset')]:
            with self.subTest(name=name):
                self.write('input.profile', content)
                result = self.shell('load_profile "$FIXTURE/input.profile"\nprintf "%s\\n" "$VM_NAME" "${TESTCONTAINERS_PORT_END-unset}"')
                self.assertEqual(result.stdout.splitlines(), [name, end])
        self.write('input.profile', 'VM_NAME=$(echo bad)\n')
        self.assertNotEqual(self.shell('load_profile "$FIXTURE/input.profile"', status=None).returncode, 0)

    def test_missing_or_unrelated_pid_is_not_a_running_vm(self):
        for pid in ('missing', 'shell'):
            with self.subTest(pid=pid):
                result = self.shell('''printf '%s\n' "$(vm_pid_file)"
if [ "$1" = shell ]; then echo $$ > "$(vm_pid_file)"; fi
vm_is_running''', pid, status=None)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('test-vm', result.stdout)

    def test_forward_mapping_contains_all_configured_ports(self):
        result = self.shell('build_forward_mappings\nbuild_netdev_value')
        for value in ('2299:22', '2375:2375', '20000:20000', '20002:20002', '9090:80',
                      'socket,id=net0,connect=127.0.0.1:19200'):
            self.assertIn(value, result.stdout)

    def test_image_reference_validation(self):
        for value, valid in [('registry.example/team/my_image:dev', True), ('image;shutdown', False)]:
            with self.subTest(value=value):
                result = self.shell('validate_image_reference "$1"', value, status=None)
                self.assertEqual(result.returncode == 0, valid)

    def test_single_vm_lock_refuses_second_claim_and_live_release(self):
        result = self.shell('''acquire_single_vm_lock
echo $$ > "$ACTIVE_LOCK_DIR/qemu.pid"
status=0; acquire_single_vm_lock || status=$?; echo "$status"
status=0; release_single_vm_lock || status=$?; echo "$status"
rm "$ACTIVE_LOCK_DIR/qemu.pid"
release_single_vm_lock''')
        statuses = result.stdout.splitlines()
        self.assertEqual(len(statuses), 2, result.stdout)
        self.assertTrue(all(int(status) != 0 for status in statuses), result.stdout)
        self.assert_missing('run/active-vm.lock')

    def test_callback_failure_releases_guard(self):
        result = self.shell('fail_update() { return 7; }\nwith_vm_state_guard fail_update', status=None)
        self.assertEqual(result.returncode, 7)
        self.assert_missing('run/vm-state.guard')

    def test_callback_signal_releases_guard(self):
        result = self.shell('terminate_update() { kill -TERM "${BASHPID:-$$}"; }\nwith_vm_state_guard terminate_update', status=None)
        self.assertNotEqual(result.returncode, 0)
        self.assert_missing('run/vm-state.guard')

    def test_stale_lock_race_preserves_single_winner(self):
        for name, value in [('qemu.pid', '99999999'), ('launcher.pid', '99999999'), ('vm-name', 'stale')]:
            self.write('race-run/active-vm.lock/' + name, value + '\n')
        (self.root / 'race-vms').mkdir()
        self.shell('''bash "$FIXTURE/bin/lock-contender.sh" "$REPOSITORY/plugins/qemu-guests/scripts/vm-utils.sh" "$FIXTURE" contender-a "$FIXTURE/result-a" "$FIXTURE/result-b" &
a=$!
bash "$FIXTURE/bin/lock-contender.sh" "$REPOSITORY/plugins/qemu-guests/scripts/vm-utils.sh" "$FIXTURE" contender-b "$FIXTURE/result-b" "$FIXTURE/result-a" &
b=$!
wait "$a"
wait "$b"''')
        self.assertCountEqual([self.read('result-a').strip(), self.read('result-b').strip()], ['won', 'blocked'])

    def test_stop_clears_stale_pid_and_lock(self):
        self.write('home/vms/test-vm.pid', '99999999\n')
        for name, value in [('qemu.pid', '99999999'), ('launcher.pid', '99999999'), ('vm-name', 'test-vm')]:
            self.write('home/run/active-vm.lock/' + name, value + '\n')
        self.shell('bash "$REPOSITORY/plugins/qemu-guests/scripts/stop-vm.sh" "$FIXTURE/test.profile"')
        self.assert_missing('home/vms/test-vm.pid')
        self.assert_missing('home/run/active-vm.lock')

    def test_stop_preserves_live_or_other_vm_ownership(self):
        for owner, vm, helper in [('qemu.pid', 'test-vm', False), ('launcher.pid', 'test-vm', False),
                                   ('launcher.pid', 'test-vm', True), ('qemu.pid', 'other-vm', False)]:
            with self.subTest(owner=owner, vm=vm, helper=helper):
                result = self.shell('''mkdir -p "$FIXTURE/home/run/active-vm.lock"
rm -f "$FIXTURE/home/run/active-vm.lock/qemu.pid" "$FIXTURE/home/run/active-vm.lock/launcher.pid"
echo $$ > "$FIXTURE/home/run/active-vm.lock/$1"
echo "$2" > "$FIXTURE/home/run/active-vm.lock/vm-name"
if [ "$3" = yes ]; then mkdir -p "$FIXTURE/home/vms"; echo owned-by-launcher > "$FIXTURE/home/vms/test-vm.gvproxy.pid"; fi
bash "$REPOSITORY/plugins/qemu-guests/scripts/stop-vm.sh" "$FIXTURE/test.profile"''', owner, vm, 'yes' if helper else 'no', status=None)
                self.assertEqual(result.returncode == 0, vm == 'other-vm', result.stderr)
                self.assertTrue((self.root / 'home/run/active-vm.lock').is_dir())
                if helper:
                    self.assertIn('launch/provisioning is in progress', result.stderr)
                    self.assertEqual(self.read('home/vms/test-vm.gvproxy.pid').strip(), 'owned-by-launcher')
                    (self.root / 'home/vms/test-vm.gvproxy.pid').unlink()

    def test_ssh_key_creation(self):
        self.shell('ensure_ssh_key')
        self.assertTrue((self.root / 'home/id_ed25519').is_file())
        self.assertTrue((self.root / 'home/id_ed25519.pub').is_file())

    def test_public_key_recovery_preserves_private_key(self):
        self.write('home/id_ed25519', 'existing-private')
        self.shell('ensure_ssh_key')
        self.assertEqual(self.read('home/id_ed25519'), 'existing-private')
        self.assertIn('recovered-public', self.read('home/id_ed25519.pub'))

    def test_public_only_key_is_not_replaced(self):
        self.write('home/id_ed25519.pub', 'existing-public')
        self.assertNotEqual(self.shell('ensure_ssh_key', status=None).returncode, 0)
        self.assertEqual(self.read('home/id_ed25519.pub'), 'existing-public')
        self.assert_missing('home/id_ed25519')

    def test_download_writes_target(self):
        self.shell('download_file https://example.invalid/file "$FIXTURE/downloaded"')
        self.assertEqual(self.read('downloaded').strip(), 'mock-content')

    def test_windows_native_path_conversion(self):
        self.assertIn('disk.qcow2', self.shell('is_windows() { return 0; }\nqemu_native_path /tmp/disk.qcow2').stdout)

    def test_accelerator_selection(self):
        cases = [('win', 'tcg', 0, 'tcg', 'max'), ('win', 'auto', 0, 'whpx', 'host'),
                 ('win', 'whpx', 0, 'whpx', 'host'), ('win', 'auto', 1, 'tcg', 'max'),
                 ('linux', 'auto', 0, 'kvm', 'host'), ('linux', 'kvm', 0, 'kvm', 'host'),
                 ('linux', 'auto', 1, 'tcg', 'max')]
        for platform, requested, probe, expected, cpu in cases:
            with self.subTest(platform=platform, requested=requested, probe=probe):
                result = self.shell('''platform_tag() { echo "$TEST_PLATFORM"; }
qemu_supports_accelerator() { return 0; }
probe_whpx() { return "$TEST_PROBE"; }
probe_kvm() { return "$TEST_PROBE"; }
VM_ACCELERATOR="$1"
configure_qemu_acceleration "$FIXTURE/bin/qemu-system-x86_64"
printf '%s\n' "$QEMU_ACCELERATOR" "${QEMU_ACCEL_ARGS[*]}"''', requested,
                                    env={'TEST_PLATFORM': platform, 'TEST_PROBE': str(probe)})
                accel = 'tcg,thread=multi' if expected == 'tcg' else expected
                self.assertEqual(result.stdout.splitlines(), [expected, f'-accel {accel} -cpu {cpu}'])

    def test_invalid_or_unavailable_accelerators_report_reason(self):
        for platform, accelerator, error in [('linux', 'kvm', '/dev/kvm'), ('win', 'kvm', 'requires a Linux host'),
                                             ('win', 'invalid', 'VM_ACCELERATOR must be auto, kvm, whpx, or tcg')]:
            with self.subTest(platform=platform, accelerator=accelerator):
                result = self.shell('''platform_tag() { echo "$TEST_PLATFORM"; }
probe_kvm() { return 1; }
VM_ACCELERATOR="$1"
configure_qemu_acceleration "$FIXTURE/bin/qemu-system-x86_64"''', accelerator,
                                    env={'TEST_PLATFORM': platform}, status=None)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(error, result.stderr)

    def test_testcontainers_command_and_metrics_validation(self):
        for config, args, error in [('', '', 'No test command provided'),
                ('TESTCONTAINERS_RESOURCE_METRICS=maybe\n', '-- true', 'TESTCONTAINERS_RESOURCE_METRICS must be auto, true, or false'),
                ('TESTCONTAINERS_RESOURCE_METRICS_INTERVAL=0\n', '-- true', 'TESTCONTAINERS_RESOURCE_METRICS_INTERVAL must be an integer from 1 to 60')]:
            with self.subTest(config=config):
                self.write('test.profile', PROFILE + config)
                result = self.shell('bash "$REPOSITORY/plugins/qemu-guests/scripts/run-test-env.sh" --profile "$FIXTURE/test.profile" ' + args, status=None)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(error, result.stderr)


class UtilitySourceContracts(unittest.TestCase):
    """Packaging/wiring assertions retained separately from runtime behavior."""
    def test_utility_modules_are_loaded(self):
        source = (PLUGIN / 'scripts/vm-utils.sh').read_text()
        for module in ('runtime', 'config', 'templates', 'qemu', 'guest', 'alpine-image', 'vm-state'):
            with self.subTest(module=module):
                self.assertTrue((PLUGIN / f'scripts/lib/{module}.sh').is_file())
                self.assertIn(f'/lib/{module}.sh', source)

    def test_connection_script_name(self):
        self.assertTrue((PLUGIN / 'scripts/connect-vm.sh').is_file())
        self.assertFalse((PLUGIN / 'scripts/sync-code.sh').exists())

    def test_provisioning_and_wrapper_wiring(self):
        contracts = json.loads((Path(__file__).parent / 'fixtures/vm-utils/source-contracts.json').read_text())
        for path, present, text, contract in contracts:
            with self.subTest(path=path, contract=contract):
                source = (PLUGIN / path).read_text()
                if present:
                    self.assertIn(text, source)
                else:
                    self.assertNotIn(text, source)


if __name__ == '__main__':
    unittest.main()
