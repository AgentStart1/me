"""Controller contracts that do not require a VM or native helper."""
import importlib.util
import io
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("control", ROOT / "scripts/gvproxy-control.py")
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


class ControllerTests(unittest.TestCase):
    def test_mapping_validation(self):
        self.assertEqual([(20000, 80), (65535, 65535)],
                         control.read_mappings(io.StringIO("20000:80\n65535:65535\n")))
        for value in ("0:80", "1:65536", "２０００:80", "20000:80\n20000:81", "1:2:3"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                control.read_mappings(io.StringIO(value))

    def test_reuses_connection_and_refuses_redirect_without_retry(self):
        connection = Mock()
        responses = [SimpleNamespace(status=status, read=lambda: b"") for status in (200, 302)]
        connection.getresponse.side_effect = responses
        with patch.object(control.http.client, "HTTPConnection", return_value=connection) as factory:
            with self.assertRaisesRegex(RuntimeError, "HTTP 302"):
                control.register_mappings(19201, [(20000, 80), (20001, 81), (20002, 82)])
        factory.assert_called_once_with("127.0.0.1", 19201, timeout=5)
        self.assertEqual(2, connection.request.call_count)
        connection.close.assert_called_once()

    def test_batch_deadline_aborts_before_request(self):
        connection = Mock()
        with patch.object(control.http.client, "HTTPConnection", return_value=connection), \
                patch.object(control.time, "monotonic", side_effect=[0, 31]):
            with self.assertRaises(TimeoutError):
                control.register_mappings(19201, [(20000, 80)])
        connection.request.assert_not_called()
        connection.close.assert_called_once()

    @unittest.skipIf(os.name == "nt", "Unix resource limits")
    def test_listener_limits_raise_soft_only_and_refuse_small_hard_limit(self):
        import resource
        with patch.object(resource, "getrlimit", return_value=(1024, 65536)), \
                patch.object(resource, "setrlimit") as setter:
            control.listener_budget(10005)
            setter.assert_called_once_with(resource.RLIMIT_NOFILE, (10261, 65536))
        with patch.object(resource, "getrlimit", return_value=(1024, 1024)), \
                patch.object(resource, "setrlimit") as setter:
            with self.assertRaisesRegex(RuntimeError, "hard limit"):
                control.listener_budget(10005)
            setter.assert_not_called()


if __name__ == "__main__":
    unittest.main()
