"""Port contracts and the actual rendered guest daemon supervisor, offline."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tests'))
from shell_test_support import ShellTestCase

SOURCE = '''export QEMU_ALPINE_BASE_DIR="$FIXTURE/state"
source "$REPOSITORY/plugins/qemu-guests/scripts/vm-utils.sh"
load_profile "$REPOSITORY/plugins/qemu-guests/profiles/dev.profile"
'''


class PortConfigurationTests(ShellTestCase):
    def test_platform_defaults(self):
        for windows in ('0', '1'):
            with self.subTest(windows=windows):
                result = self.run_shell(SOURCE + '''is_windows() { return "$1"; }
load_profile "$REPOSITORY/plugins/qemu-guests/profiles/dev.profile"
printf '%s\n' "$TESTCONTAINERS_PORT_END"
build_forward_mappings | wc -l
build_netdev_value'''.replace('return "$1"', 'return ' + windows))
                self.assertEqual([line.strip() for line in result.stdout.splitlines()],
                                 ['20127', '133', 'socket,id=net0,connect=127.0.0.1:19200'])

    def test_automatic_pool_follows_start_without_stale_forwards(self):
        self.write('shifted.profile', 'TESTCONTAINERS_PORT_START=21000\nTESTCONTAINERS_PORT_END=auto\n')
        result = self.run_shell(SOURCE + '''load_profile "$FIXTURE/shifted.profile"
printf '%s\n' "$TESTCONTAINERS_PORT_END"
build_forward_mappings | wc -l''')
        self.assertEqual([line.strip() for line in result.stdout.splitlines()], ['21127', '130'])

    def test_automatic_pool_overflow_is_rejected(self):
        self.write('overflow.profile', 'TESTCONTAINERS_PORT_START=65500\nTESTCONTAINERS_PORT_END=auto\n')
        self.assertNotEqual(self.run_shell(SOURCE + 'load_profile "$FIXTURE/overflow.profile"', status=None).returncode, 0)

    def test_explicit_pool_sizes_through_protocol_maximum(self):
        for end, count in ((29999, 10005), (20511, 517), (20512, 518), (65535, 45541)):
            with self.subTest(end=end):
                result = self.run_shell(SOURCE + 'TESTCONTAINERS_PORT_START=20000 TESTCONTAINERS_PORT_END="$1"\nbuild_forward_mappings | wc -l', end)
                self.assertEqual(int(result.stdout), count)

    def test_forward_collisions_are_rejected(self):
        for forward in ('2222:80', '2375:80', '20000:80', '9090:80,9090:81'):
            with self.subTest(forward=forward):
                result = self.run_shell(SOURCE + 'TESTCONTAINERS_PORT_END=20015 PORT_FORWARD="$1"\nbuild_netdev_value', forward, status=None)
                self.assertNotEqual(result.returncode, 0)

    def test_invalid_pool_bounds_are_rejected(self):
        for start, end in ((0, 15), (20000, 65536), (20001, 20000), (1, 1000), (1024, 65535)):
            with self.subTest(start=start, end=end):
                result = self.run_shell(SOURCE + 'PORT_FORWARD= TESTCONTAINERS_PORT_START="$1" TESTCONTAINERS_PORT_END="$2"\nbuild_netdev_value', start, end, status=None)
                self.assertNotEqual(result.returncode, 0)

    def test_outbound_pool_excludes_published_ports(self):
        for start, end, expected in ((20000, 20015, '32768 60999'), (32768, 33279, '33280 60999'),
                                     (60488, 60999, '32768 60487'), (32768, 60999, '1024 32767'),
                                     (1024, 65534, '65535 65535'), (1024, 65535, None)):
            with self.subTest(start=start, end=end):
                result = self.run_shell(SOURCE + 'TESTCONTAINERS_PORT_START="$1" TESTCONTAINERS_PORT_END="$2"\nguest_outbound_port_range', start, end, status=None)
                if expected is None:
                    self.assertNotEqual(result.returncode, 0)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), expected)

    def test_guest_docker_api_collision_is_rejected(self):
        result = self.run_shell(SOURCE + 'TESTCONTAINERS_PORT_START=2300 TESTCONTAINERS_PORT_END=2400 DOCKER_DAEMON_PORT=12375\nbuild_forward_mappings', status=None)
        self.assertNotEqual(result.returncode, 0)

    def test_guest_pool_verification_rejects_failed_remote_probes(self):
        for command in ('wait_for_docker_publish_pool', 'verify_docker_publish_pool'):
            with self.subTest(command=command):
                result = self.run_shell(SOURCE + 'ssh_exec() { return 1; }\n' + command, status=None)
                self.assertNotEqual(result.returncode, 0)


class DaemonSupervisorTests(ShellTestCase):
    def setUp(self):
        super().setUp()
        self.install_mocks(Path(__file__).parent / 'fixtures/port-ranges')
        self.env['MOCK_DIR'] = self.path(self.root)
        self.run_shell(SOURCE + '''render_template "$REPOSITORY/plugins/qemu-guests/templates/dockerd-with-port-range.sh.tpl" "$FIXTURE/wrapper" \
TESTCONTAINERS_PORT_START 20000 TESTCONTAINERS_PORT_END 20015 OUTBOUND_PORT_START 32768 OUTBOUND_PORT_END 60999''')
        # Redirect only absolute guest paths; execute the real rendered template.
        wrapper = self.read('wrapper').replace('/usr/bin/dockerd', 'mock-dockerd').replace('/usr/bin/docker', 'mock-docker')
        self.write('wrapper', wrapper.replace('/run/qemu-docker-publish-pool.ready', self.path(self.root / 'publish-ready')))

    def wrapper(self, **env):
        return self.run_shell('exec bash "$FIXTURE/wrapper"', env=env, status=None)

    def assert_restored(self):
        self.assertEqual(self.read('current-range').strip(), 'net.ipv4.ip_local_port_range=32768 60999')

    def test_ready_daemon_seeds_allocator_then_restores_outbound_range(self):
        self.assertEqual(self.wrapper().returncode, 7)
        for name in ('cached-range', 'cache-on-mapping'):
            self.assertEqual(self.read(name).strip(), 'net.ipv4.ip_local_port_range=20000 20015')
        self.assert_restored()

    def test_daemon_startup_failure_preserves_status_and_restores_outbound(self):
        result = self.wrapper(FAIL_DAEMON='1')
        self.assertEqual(result.returncode, 42)
        self.assertIn('exited before initializing', result.stderr)
        self.assert_restored()

    def test_wrong_automatic_pool_aborts_and_cleans_seed_container(self):
        result = self.wrapper(PROBE_PORT='40000')
        self.assertEqual(result.returncode, 1)
        self.assertIn('outside the QEMU forwarding range', result.stderr)
        self.assertIn('rm -f seed-container', self.read('seed-cleanup'))

    def test_existing_mapping_needs_no_spare_port(self):
        self.assertEqual(self.wrapper(EXISTING_MAPPING='1').returncode, 7)
        self.assert_missing('cache-on-mapping')

    def test_restore_failure_is_not_hidden(self):
        self.assertEqual(self.wrapper(FAIL_RESTORE='1').returncode, 1)

    def test_termination_clears_readiness_and_joins_child(self):
        process = self.start_shell('exec bash "$FIXTURE/wrapper"', env={'WAIT_DAEMON': '1'})
        self.wait_until(lambda: (self.root / 'publish-ready').exists())
        self.assertEqual(self.read('publish-ready').strip(), '20000 20015')
        self.signal_shell()
        self.assertEqual(process.wait(timeout=15), 143)
        self.assert_missing('publish-ready')
        self.assertNotEqual(self.run_shell('kill -0 "$(cat "$FIXTURE/daemon.pid")"', status=None).returncode, 0)


if __name__ == '__main__':
    unittest.main()
