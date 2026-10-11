"""Native process identity and signalling, shared by QEMU and gvproxy."""
import ctypes
import os
from pathlib import Path
import signal
import subprocess
import shutil
import time

TIMEOUT = 2

def identity(pid):
    if type(pid) is not int or not 0 < pid < 2**32:
        raise ValueError("Invalid native process ID")
    if os.name == "nt":
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:
                return None
            raise OSError(ctypes.get_last_error(), "Cannot inspect gvproxy process")
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        try:
            exit_code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                raise OSError("Cannot inspect gvproxy exit state")
            if exit_code.value != 259:
                return None
            size = wintypes.DWORD(32768)
            name = ctypes.create_unicode_buffer(size.value)
            creation, end, cpu, user = (wintypes.FILETIME() for _ in range(4))
            if not kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size)) or not kernel.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(end), ctypes.byref(cpu), ctypes.byref(user)):
                raise OSError("Cannot verify gvproxy executable/start time")
            return [os.path.normcase(name.value), (creation.dwHighDateTime << 32) | creation.dwLowDateTime]
        finally:
            kernel.CloseHandle(handle)
    try:
        stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        if stat[0] == "Z":
            return None
        return [os.path.realpath(f"/proc/{pid}/exe"), stat[19]]
    except FileNotFoundError:
        return None



def terminate(record, timeout=10):
    """Hold an OS process reference so PID reuse cannot redirect the signal."""
    pid = record["pid"]
    if os.name == "nt":
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        handle = kernel.OpenProcess(0x1000 | 0x100000 | 1, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:
                return
            raise OSError(ctypes.get_last_error(), "Cannot open owned process for termination")
        try:
            # The open handle pins this native process; PID reuse cannot replace it.
            if identity(pid) != record["identity"]:
                raise RuntimeError("Process identity changed; refusing to signal another process")
            if not kernel.TerminateProcess(handle, 1):
                raise OSError(ctypes.get_last_error(), "Cannot terminate owned process")
            if kernel.WaitForSingleObject(handle, int(timeout * 1000)) != 0:
                raise RuntimeError("Owned process did not exit; retaining ownership state")
        finally:
            kernel.CloseHandle(handle)
        return
    current = identity(pid)
    if current is None:
        return
    fd = os.pidfd_open(pid)
    try:
        if identity(pid) != record["identity"]:
            raise RuntimeError("Process identity changed; refusing to signal another process")
        signal.pidfd_send_signal(fd, signal.SIGTERM)
        deadline = time.monotonic() + timeout
        while identity(pid) == record["identity"]:
            if time.monotonic() > deadline:
                signal.pidfd_send_signal(fd, signal.SIGKILL)
                break
            time.sleep(0.1)
    finally:
        os.close(fd)


def write_record(path, record):
    """Replace a complete ownership record atomically."""
    import json
    import tempfile
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as output:
            json.dump(record, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def owns_listeners(pid, ports):
    """Prove readiness belongs to the launched process, not a racing port owner."""
    if os.name == "nt":
        values = ",".join(str(int(port)) for port in ports)
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                                 f"$ports=@({values}); Get-NetTCPConnection -State Listen -ErrorAction Stop | "
                                 f"Where-Object {{$_.OwningProcess -eq {int(pid)} -and $_.LocalAddress -eq '127.0.0.1' -and $_.LocalPort -in $ports}} | "
                                 "Select-Object -ExpandProperty LocalPort | ConvertTo-Json -Compress"],
                                check=True, capture_output=True, text=True, timeout=5)
        import json
        found = json.loads(result.stdout) if result.stdout.strip() else []
        return set(found if isinstance(found, list) else [found]) == set(ports)
    sockets = set()
    for entry in Path(f"/proc/{pid}/fd").iterdir():
        try:
            link = os.readlink(entry)
        except FileNotFoundError:
            continue
        if link.startswith("socket:["):
            sockets.add(link[8:-1])
    found = set()
    for row in Path("/proc/net/tcp").read_text().splitlines()[1:]:
        fields = row.split()
        address, port = fields[1].split(":")
        if fields[3] == "0A" and address == "0100007F" and fields[9] in sockets:
            found.add(int(port, 16))
    return set(ports).issubset(found)


def windows_pid(pid, strict=False):
    """Translate a Git Bash/MSYS PID before verifying its native executable."""
    try:
        ps = os.environ.get("QEMU_MSYS_PS_BIN") or shutil.which("ps")
        if not ps:
            bash = shutil.which("bash")
            candidate = Path(bash).resolve().parent.parent / "usr/bin/ps.exe" if bash else None
            ps = str(candidate) if candidate and candidate.is_file() else "ps"
        result = subprocess.run([ps, "-W"], capture_output=True, text=True,
                                timeout=TIMEOUT, check=True)
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 4 and fields[0] == str(pid) and fields[3].isdecimal():
                return int(fields[3])
    except (OSError, subprocess.SubprocessError):
        if strict:
            raise
    return pid
