"""Shared ADB read helpers. Generated copies: edit scripts/android-status/android_probe.py."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import subprocess

TIMEOUT = 5
MAX_DEVICES = 64


class ProbeError(RuntimeError):
    pass


def native_path(value):
    if os.name == "nt" and str(value).startswith("/"):
        try:
            return subprocess.run(["cygpath", "-w", str(value)], capture_output=True, text=True,
                                  timeout=TIMEOUT, check=True).stdout.strip()
        except (OSError, subprocess.SubprocessError) as error:
            raise ProbeError("Cannot convert Android path to a native Windows path") from error
    return str(value)


def adb_command():
    override = os.environ.get("ANDROID_ADB_COMMAND")
    if override:
        return native_path(override)
    found = shutil.which("adb")
    if found:
        return found
    root = Path(native_path(os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or Path.home() / "android-sdk"))
    path = root / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
    if path.is_file():
        return str(path)
    raise ProbeError("ADB is unavailable. Set ANDROID_HOME or ANDROID_ADB_COMMAND.")


def validate_serial(serial):
    if not isinstance(serial, str) or not re.fullmatch(r"[A-Za-z0-9\[][A-Za-z0-9._:\[\]%-]{0,255}", serial):
        raise ProbeError("Invalid ADB serial")
    return serial


def adb(args, serial=None, binary=False):
    command = [adb_command()]
    if serial is not None:
        command += ["-s", validate_serial(serial)]
    try:
        result = subprocess.run(command + list(args), capture_output=True, timeout=TIMEOUT, check=False)
    except subprocess.TimeoutExpired as error:
        raise ProbeError("ADB probe timed out") from error
    except OSError as error:
        raise ProbeError("ADB could not be started") from error
    if result.returncode:
        # Never echo device output or a metadata file into an error message.
        raise ProbeError("ADB command failed; the device may be disconnected or unauthorized")
    limit = 8 * 1024 * 1024 if binary else 512 * 1024
    if len(result.stdout) > limit:
        raise ProbeError("ADB response exceeds the size limit")
    return result.stdout if binary else result.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n")


def devices(warnings=None):
    warnings = warnings if warnings is not None else []
    output = adb(["devices", "-l"])
    result = []
    for line in output.splitlines():
        if not line.strip() or line.startswith(("List of devices", "*")):
            continue
        fields = line.split()
        if len(fields) < 2:
            warnings.append("Skipped a malformed ADB device record")
            continue
        serial, connection = fields[:2]
        if fields[1:3] == ["no", "permissions"]:
            connection = "no permissions"
        try:
            validate_serial(serial)
        except ProbeError:
            warnings.append("Skipped an ADB device record with an unsupported serial")
            continue
        values = dict(item.split(":", 1) for item in fields[2:] if ":" in item)
        result.append({"serial": serial, "connection": connection,
                       "model": values.get("model", "").replace("_", " ")[:200]})
    return result


def collect_devices(inspect):
    warnings = []
    try:
        found = devices(warnings)
    except ProbeError as error:
        return {"state": "unavailable", "detail": str(error)}, [], []
    if len(found) > MAX_DEVICES:
        warnings.append(f"Only the first {MAX_DEVICES} devices are shown")
    with ThreadPoolExecutor(max_workers=8) as pool:
        items = list(pool.map(inspect, found[:MAX_DEVICES]))
    return {"state": "available", "detail": "ADB device list received"}, [item for item in items if item is not None], warnings


def observed_at():
    return datetime.now(timezone.utc).isoformat()
