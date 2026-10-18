"""Scoped command lifetime and cancellation handoffs in private fixtures."""
import os
import sys
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import command_tree as module

class CommandTreeTests(unittest.TestCase):
    def test_cancellation_during_creation_keeps_cleanup_ownership(self):
        class Cancelled(Exception):
            pass
        tree = module.CommandTree()
        original = subprocess.Popen
        def create(*args, **kwargs):
            child = original(*args, **kwargs)
            signal.raise_signal(signal.SIGTERM)
            return child
        def cancel(number, frame):
            raise Cancelled()
        previous = signal.signal(signal.SIGTERM, cancel)
        try:
            with patch.object(module.subprocess, 'Popen', side_effect=create):
                with self.assertRaises(Cancelled):
                    tree.start([sys.executable, '-c', 'import time;time.sleep(60)'])
            self.assertIsNotNone(tree.backend.child)
        finally:
            signal.signal(signal.SIGTERM, previous)
            tree.stop()
        self.assertIsNotNone(tree.backend.child.poll())

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
