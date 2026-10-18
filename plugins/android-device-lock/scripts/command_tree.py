"""Owned command scopes: process groups on Unix, gated Job Objects on Windows."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


class PosixCommandTree:
    def __init__(self):
        self.child = None

    def start(self, command):
        self.child = subprocess.Popen(command, start_new_session=True)
        return self.child

    def stop(self):
        if self.child is None:
            return
        try:
            os.killpg(self.child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            self.child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        # Root exit is not proof that its process group has stopped.
        try:
            os.killpg(self.child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.child.wait(timeout=5)


class WindowsCommandTree:
    def __init__(self):
        self.child = None
        self.job = None
        self.gate = None

    def start(self, command):
        import ctypes
        from ctypes import wintypes

        class Limits(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                        ("flags", wintypes.DWORD), ("minimum", ctypes.c_size_t),
                        ("maximum", ctypes.c_size_t), ("active", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                        ("scheduling", wintypes.DWORD)]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("basic", Limits), ("io", ctypes.c_uint64 * 6),
                        ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                        ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        for name, arguments, result in (
            ("CreateJobObjectW", [ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            ("SetInformationJobObject", [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
            ("AssignProcessToJobObject", [wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            ("TerminateJobObject", [wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            ("QueryInformationJobObject", [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p], wintypes.BOOL),
            ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
        ):
            function = getattr(self.api, name)
            function.argtypes, function.restype = arguments, result
        self.job = self.api.CreateJobObjectW(None, None)
        if not self.job:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.gate = tempfile.TemporaryDirectory(prefix="android-command-")
        gate = Path(self.gate.name) / "start"
        # No user code can spawn descendants until assignment to the job succeeds.
        worker = Path(__file__).with_name("command-worker.py")
        self.child = subprocess.Popen([sys.executable, str(worker), str(gate), *command],
                                      creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        if not self.api.AssignProcessToJobObject(self.job, int(self.child._handle)):
            raise ctypes.WinError(ctypes.get_last_error())
        gate.touch()
        return self.child

    def stop(self):
        try:
            if self.job:
                self._stop_job()
            if self.child is not None:
                if self.child.poll() is None:
                    # Assignment failure leaves only a gated wrapper outside the job.
                    self.child.kill()
                self.child.wait(timeout=5)
        finally:
            if self.job:
                self.api.CloseHandle(self.job)
                self.job = None
            if self.gate:
                self.gate.cleanup()
                self.gate = None

    def _stop_job(self):
        import ctypes
        class Accounting(ctypes.Structure):
            _fields_ = [("times", ctypes.c_int64 * 4), ("page_faults", ctypes.c_uint32),
                        ("total", ctypes.c_uint32), ("active", ctypes.c_uint32),
                        ("terminated", ctypes.c_uint32)]
        accounting = Accounting()
        if not self.api.TerminateJobObject(self.job, 1):
            raise ctypes.WinError(ctypes.get_last_error())
        deadline = time.monotonic() + 5
        while True:
            if not self.api.QueryInformationJobObject(self.job, 1, ctypes.byref(accounting),
                                                       ctypes.sizeof(accounting), None):
                raise ctypes.WinError(ctypes.get_last_error())
            if accounting.active == 0:
                break
            if time.monotonic() >= deadline:
                raise OSError("Command job did not stop; lease retained")
            time.sleep(.01)


class CommandTree:
    """Stop all owned work before the caller may release its device lease.

    start() may partially succeed: always call stop(), including on startup error.
    stop() raises if termination cannot be confirmed; callers must retain the lease.
    Unix children must remain in their original process group.
    """
    def __init__(self):
        self.backend = WindowsCommandTree() if os.name == "nt" else PosixCommandTree()

    def start(self, command):
        return self.backend.start(command)

    def stop(self):
        self.backend.stop()
