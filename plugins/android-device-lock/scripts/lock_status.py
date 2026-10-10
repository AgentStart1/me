"""Inspect the existing device-side lease without acquiring, renewing, or removing it."""
import json
import os
import posixpath
import shlex
import time
from android_probe import ProbeError, adb, collect_devices, observed_at

DEFAULT_LOCK_PATH = "/data/local/tmp/android-device-test.lock.d"


def lock_path():
    value = os.environ.get("ANDROID_DEVICE_LOCK_PATH") or DEFAULT_LOCK_PATH
    if not value.startswith("/") or any(char in value for char in ("\n", "\r", "\0")) or len(value) > 1024:
        raise ProbeError("ANDROID_DEVICE_LOCK_PATH must be an absolute Android path")
    return value.rstrip("/") or "/"


def read_command(path):
    directory, metadata, parent = map(shlex.quote, [path, path + "/lock.json", posixpath.dirname(path)])
    return (f"if [ -d {directory} ]; then printf 'present\\n'; cat {metadata} 2>/dev/null; "
            f"elif [ -e {directory} ]; then printf 'invalid\\n'; "
            f"elif [ -d {parent} ] && [ -x {parent} ]; then printf 'absent\\n'; "
            "else printf 'unknown\\n'; fi")


def parse_lock(output, now):
    header, _, raw = output.partition("\n")
    if header.strip() == "absent":
        return {"state": "free", "detail": "No lock directory at observation time"}
    if header.strip() != "present":
        return {"state": "unknown", "detail": "Lock path is inaccessible or has an unexpected type"}
    try:
        metadata = json.loads(raw)
        if not isinstance(metadata, dict):
            raise ValueError()
        expiry = metadata.get("expires_at_epoch")
        if type(expiry) is not int or expiry < 0 or expiry > 253402300799:
            raise ValueError()
        # Whitelist display fields. Never return owner_token or full project paths.
        project = str(metadata.get("project_dir", "")).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        return {"state": "expired" if expiry <= now else "held", "expiresAt": expiry,
                "remainingSeconds": max(0, int(expiry - now)), "host": str(metadata.get("host", ""))[:200],
                "pid": metadata.get("pid") if type(metadata.get("pid")) is int else None,
                "task": str(metadata.get("test_name", ""))[:300], "project": project[:200],
                "acquiredAt": str(metadata.get("acquired_at_utc", ""))[:80]}
    except (ValueError, TypeError):
        return {"state": "unknown", "detail": "Lock exists but metadata is incomplete or unreadable; treat the device as occupied"}


def inspect_device(device, path):
    if device["connection"] != "device":
        return {**device, "lock": {"state": "unavailable", "detail": "Device is not online; lock ownership is unknown"}}
    try:
        result = parse_lock(adb(["shell", read_command(path)], device["serial"]), time.time())
    except ProbeError as error:
        result = {"state": "unavailable", "detail": str(error)}
    return {**device, "lock": result}


def collect_status():
    path = lock_path()
    adb_status, items, warnings = collect_devices(lambda device: inspect_device(device, path))
    # Earlier probes may expire while waiting for the remaining devices.
    now = time.time()
    for item in items:
        lease = item["lock"]
        if lease["state"] in ("held", "expired"):
            lease["state"] = "expired" if lease["expiresAt"] <= now else "held"
            lease["remainingSeconds"] = max(0, int(lease["expiresAt"] - now))
    return {"observedAt": observed_at(), "adb": adb_status, "devices": items, "lockPath": path,
            "warnings": warnings, "clockNote": "Lease expiry uses this host's clock. No waiting queue is recorded by the lock helper."}


if __name__ == "__main__":
    print(json.dumps(collect_status(), indent=2))
