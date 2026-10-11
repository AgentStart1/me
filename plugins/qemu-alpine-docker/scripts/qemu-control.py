"""Verify persisted QEMU identity before inspecting or stopping a VM."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from process_identity import identity, terminate, write_record
from process_identity import windows_pid


def probe(pid, name):
    native = windows_pid(pid, strict=True) if os.name == "nt" else pid
    current = identity(native)
    if current is None or Path(current[0]).name.lower() not in ("qemu-system-x86_64", "qemu-system-x86_64.exe"):
        return None
    if os.name == "nt":
        command = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                                  f"(Get-CimInstance Win32_Process -Filter 'ProcessId={native}').CommandLine"],
                                 capture_output=True, text=True, check=True, timeout=5).stdout
        match = re.search(r'(?:^|\s)-name\s+"?([A-Za-z0-9_.-]+)(?:,|"|\s|$)', command)
        actual_name = match.group(1) if match else None
    else:
        args = Path(f"/proc/{native}/cmdline").read_bytes().decode().split("\0")
        actual_name = args[args.index("-name") + 1].split(",")[0] if "-name" in args else None
    if actual_name not in (name, name + "-install", name + "-verify"):
        return None
    return {"pid": native, "shell_pid": pid, "identity": current}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["probe", "record", "stop"])
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--state", required=True)
    args = parser.parse_args()
    state = Path(args.state)
    if state.exists() and args.action != "record":
        record = json.loads(state.read_text())
        current = identity(record["pid"])
        valid = record.get("shell_pid") == args.pid and current == record["identity"]
    else:
        record = probe(args.pid, args.name)
        valid = record is not None
    if args.action == "record":
        if not valid:
            raise RuntimeError("Cannot register a missing or unrelated QEMU process")
        write_record(state, record)
    elif args.action == "stop":
        if valid:
            terminate(record)
        # A reused PID is stale VM state, never a reason to terminate that process.
    elif not valid:
        sys.exit(1)


if __name__ == "__main__":
    main()
