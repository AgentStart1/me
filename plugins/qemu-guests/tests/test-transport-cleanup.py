"""Transport ownership drains all child cleanup without starting SSH or QEMU."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from resource_ownership import Cancelled
from test_environment_owner import TestEnvironmentOwner
from test_guest_transport import GuestTransport, TransportCleanupError
from test_linux_transport import LinuxTransport


class TransportCleanupTests(unittest.TestCase):
    def transport(self, kind=GuestTransport):
        transport = object.__new__(kind)
        transport.children = [object(), object(), object()]
        transport.stop = Mock()
        return transport

    def test_success_stops_all_children_in_reverse_order(self):
        for kind in (GuestTransport, LinuxTransport):
            with self.subTest(kind=kind):
                transport = self.transport(kind)
                transport.close()
                self.assertEqual([call.args[0] for call in transport.stop.call_args_list],
                                 transport.children[::-1])

    def test_failure_does_not_skip_remaining_children(self):
        transport = self.transport()
        failure = OSError('synthetic stop failure')
        transport.stop.side_effect = [failure, None, None]
        with self.assertRaises(TransportCleanupError) as raised:
            transport.close()
        self.assertEqual(transport.stop.call_count, 3)
        self.assertEqual(raised.exception.failures, (failure,))

    def test_multiple_failures_are_preserved_in_cleanup_order(self):
        transport = self.transport()
        failures = [OSError('first'), TimeoutError('second')]
        transport.stop.side_effect = [failures[0], None, failures[1]]
        with self.assertRaises(TransportCleanupError) as raised:
            transport.close()
        self.assertEqual(raised.exception.failures, tuple(failures))
        self.assertIs(raised.exception.__cause__, failures[0])

    def test_cancellation_is_rethrown_after_remaining_cleanup(self):
        for cancellation in (KeyboardInterrupt(), SystemExit(7), Cancelled(2)):
            with self.subTest(kind=type(cancellation)):
                transport = self.transport()
                failure = OSError('another stop failed')
                transport.stop.side_effect = [cancellation, failure, None]
                with self.assertRaises(type(cancellation)) as raised:
                    transport.close()
                self.assertIs(raised.exception, cancellation)
                self.assertEqual(transport.stop.call_count, 3)
                self.assertEqual(raised.exception.__cause__.failures, (cancellation, failure))

    def test_failed_cleanup_retains_environment_lease_after_draining_children(self):
        with tempfile.TemporaryDirectory() as directory:
            transport = self.transport()
            transport.stop.side_effect = [OSError('stop failed'), None, None]
            with self.assertRaises(TransportCleanupError):
                with TestEnvironmentOwner(directory) as owner:
                    owner.callback(transport.close)
            record = json.loads((Path(directory) / 'test-environment.lock/owner.json').read_text())
            self.assertEqual(record['phase'], 'cleanup-uncertain')
            self.assertEqual(transport.stop.call_count, 3)

    def test_empty_transport_closes_successfully(self):
        transport = self.transport()
        transport.children = []
        transport.close()
        transport.stop.assert_not_called()


if __name__ == '__main__':
    unittest.main()
