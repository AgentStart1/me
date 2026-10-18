"""Native controller contracts without contacting an adb device."""
import argparse
import importlib.util
from pathlib import Path
import os
import signal
import subprocess
import sys
import tempfile
import time
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

    def test_explicit_shell_command_path(self):
        with tempfile.TemporaryDirectory(prefix='lease command ') as directory:
            entry = Path(directory) / 'gradlew'
            entry.write_text('#!/usr/bin/env bash\nexit 17\n', encoding='utf-8', newline='\n')
            entry.chmod(0o755)
            command = module.host_command([str(entry)])
            self.assertEqual(subprocess.run(command).returncode, 17)

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

    def test_cleanup_failure_retains_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = self.controller(directory)
            with patch.object(controller, "acquire"), patch.object(controller, "mutate") as release, \
                 patch.object(module, "CommandTree") as tree:
                tree.return_value.start.return_value.wait.return_value = 0
                tree.return_value.stop.side_effect = OSError("fixture cleanup failure")
                self.assertEqual(controller.run(["fixture"]), 1)
                release.assert_not_called()

    def test_python_shebang_preserves_arguments(self):
        with tempfile.TemporaryDirectory(prefix="lease script ") as directory:
            entry = Path(directory) / "python-entry"
            interpreter = "python" if os.name == "nt" else "python3"
            entry.write_text(f"#!/usr/bin/env {interpreter}\nimport sys\n"
                             "assert sys.argv[1:] == ['space quote \" $value', '']\n"
                             "sys.exit(17)\n", encoding="utf-8", newline="\n")
            entry.chmod(0o755)
            self.assertEqual(subprocess.run(module.host_command(
                [str(entry), 'space quote " $value', ''])).returncode, 17)

    def test_missing_command_preserves_status(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = self.controller(directory)
            with patch.object(controller, "acquire"), patch.object(controller, "mutate") as release:
                self.assertEqual(controller.run([str(Path(directory) / "missing-command")]), 127)
                release.assert_called_once()

    def test_native_signal_dispatch_during_real_child_wait(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token = root / 'owner.token'
            ready = root / 'ready'
            harness = root / 'harness.py'
            harness.write_text(
                'import importlib.util,sys\nfrom pathlib import Path\n'
                f'spec=importlib.util.spec_from_file_location("lease", {str(ENTRY)!r})\n'
                'lease=importlib.util.module_from_spec(spec); spec.loader.exec_module(lease)\n'
                'class Fixture(lease.Controller):\n'
                ' def acquire(self): self.token_file.write_text("fixture")\n'
                ' def mutate(self): self.token_file.unlink()\n'
                'lease.Controller=Fixture\n'
                'sys.exit(lease.main())\n', encoding='utf-8')
            heartbeat = root / 'heartbeat'
            worker = root / 'worker.py'
            worker.write_text(
                'import signal,time,sys\nfrom pathlib import Path\n'
                'signal.signal(signal.SIGBREAK if sys.platform == "win32" else signal.SIGTERM, signal.SIG_IGN)\n'
                'while True:\n Path(sys.argv[1]).write_text(str(time.monotonic()))\n time.sleep(.02)\n',
                encoding='utf-8')
            child_command = (f'import subprocess,sys,time\nfrom pathlib import Path\n'
                             f'subprocess.Popen([sys.executable, {str(worker)!r}, {str(heartbeat)!r}])\n'
                             f'while not Path({str(heartbeat)!r}).exists(): time.sleep(.01)\n'
                             f'Path({str(ready)!r}).touch()\ntime.sleep(60)')
            command = [sys.executable, str(harness), 'run', '--token-file', str(token), '--', sys.executable, '-c', child_command]
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
            try:
                deadline = time.monotonic() + 10
                while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(.05)
                self.assertTrue(ready.exists())
                process.send_signal(signal.CTRL_BREAK_EVENT if os.name == 'nt' else signal.SIGTERM)
                self.assertEqual(process.wait(timeout=10), 128 + (signal.SIGBREAK if os.name == 'nt' else signal.SIGTERM))
                self.assertFalse(token.exists())
                before = heartbeat.read_text()
                time.sleep(.2)
                self.assertEqual(heartbeat.read_text(), before, "descendant survived release")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()

    @unittest.skipUnless(os.name == "nt", "Windows Job Object contract")
    def test_assignment_failure_never_starts_user_command(self):
        import ctypes
        from unittest.mock import Mock
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.AssignProcessToJobObject = Mock(return_value=0)
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "must-not-run"
            tree = module.CommandTree()
            try:
                with patch.object(ctypes, "WinDLL", return_value=api):
                    with self.assertRaises(OSError):
                        tree.start([sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).touch()"])
            finally:
                tree.stop()
            self.assertFalse(marker.exists())

    def test_cleanup_restores_signal_handlers(self):
        before = {number: signal.getsignal(number) for number in module.cancellation_signals()}
        with self.assertRaises(OSError):
            with module.protected_cleanup():
                self.assertTrue(all(signal.getsignal(number) == signal.SIG_IGN for number in before))
                raise OSError("fixture")
        self.assertEqual({number: signal.getsignal(number) for number in before}, before)

    def test_root_exit_does_not_abandon_descendants(self):
        with tempfile.TemporaryDirectory() as directory:
            heartbeat = Path(directory) / "heartbeat"
            worker = ("import signal,time\nfrom pathlib import Path\n"
                      "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
                      f"while True:\n Path({str(heartbeat)!r}).write_text(str(time.monotonic()))\n time.sleep(.02)\n")
            parent = ("import subprocess,sys,time\nfrom pathlib import Path\n"
                      f"subprocess.Popen([sys.executable,'-c',{worker!r}])\n"
                      f"while not Path({str(heartbeat)!r}).exists(): time.sleep(.01)\n")
            tree = module.CommandTree()
            try:
                child = tree.start([sys.executable, "-c", parent])
                self.assertEqual(child.wait(timeout=10), 0)
            finally:
                tree.stop()
            before = heartbeat.read_text()
            time.sleep(.2)
            self.assertEqual(heartbeat.read_text(), before)


if __name__ == "__main__":
    unittest.main()
