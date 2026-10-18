"""Native controller contracts without contacting an adb device."""
import argparse
import importlib.util
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ENTRY = Path(__file__).resolve().parents[1] / "scripts/adb-device-lock.py"
spec = importlib.util.spec_from_file_location("lease_controller", ENTRY)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ControllerTests(unittest.TestCase):
    def controller(self, directory):
        return module.Controller(argparse.Namespace(lock_path="/data/local/tmp/test.lock.d", serial="fixture",
            token_file=str(Path(directory) / "owner.token"), project_dir="fixture", test_name="quoted ' 名称",
            max_timeout_seconds=30, wait_timeout_seconds=0, poll_seconds=1))

    def test_metadata_import_has_no_cli_side_effects(self):
        self.assertTrue(callable(module.metadata.decode))

    def test_native_entry_and_validation(self):
        result = subprocess.run([sys.executable, str(ENTRY), "--help"], capture_output=True)
        self.assertEqual(result.returncode, 0)
        for arguments in (("run",), ("acquire", "--lock-path", "/data/local/tmp/../other"),
                          ("acquire", "--poll-seconds", "0")):
            self.assertEqual(subprocess.run([sys.executable, str(ENTRY), *arguments], capture_output=True).returncode, 2)

    def test_publication_failure_retains_token_when_remote_delete_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = self.controller(directory)
            with patch.object(controller, "connected"), patch.object(controller, "shell", return_value=subprocess.CompletedProcess([], 0)), \
                 patch.object(controller, "publish", side_effect=module.LeaseError("publication failed", 2)), \
                 patch.object(controller, "remove", return_value=False):
                with self.assertRaises(module.LeaseError):
                    controller.acquire()
            self.assertTrue(controller.token_file.read_text().strip())

    def test_child_status_and_cleanup_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            for command_status in (0, 23):
                controller = self.controller(directory)
                with patch.object(controller, "acquire"), patch.object(controller, "mutate", side_effect=module.LeaseError("delete failed")):
                    self.assertEqual(controller.run([sys.executable, "-c", f"raise SystemExit({command_status})"]), command_status or 1)

    def test_cancellation_stops_owned_child_before_releasing(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = self.controller(directory)
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=sys.platform != "win32")
            original_wait = child.wait
            original_popen = subprocess.Popen
            calls = 0
            def wait(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise module.Cancelled(signal.SIGTERM)
                return original_wait(*args, **kwargs)
            try:
                with patch.object(controller, "acquire"), patch.object(controller, "mutate") as release, \
                     patch.object(module.subprocess, "Popen", side_effect=lambda command, **kwargs: child if command == ["fixture"] else original_popen(command, **kwargs)), patch.object(child, "wait", side_effect=wait):
                    self.assertEqual(controller.run(["fixture"]), 143)
                    release.assert_called_once()
                self.assertIsNotNone(child.poll())
            finally:
                if child.poll() is None:
                    child.kill()
                    original_wait()


if __name__ == "__main__":
    unittest.main()
