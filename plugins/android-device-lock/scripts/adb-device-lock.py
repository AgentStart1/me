#!/usr/bin/env python3
"""Host lease owner; all remote mutations use the shared device-side guard."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from string import Template
import uuid

spec = importlib.util.spec_from_file_location("lock_metadata", Path(__file__).with_name("lock-metadata.py"))
metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metadata)


spec = importlib.util.spec_from_file_location("command_tree", Path(__file__).with_name("command_tree.py"))
command_tree = importlib.util.module_from_spec(spec)
spec.loader.exec_module(command_tree)
CommandTree = command_tree.CommandTree


class LeaseError(Exception):
    def __init__(self, message, status=1):
        super().__init__(message)
        self.status = status


class Cancelled(Exception):
    def __init__(self, number):
        self.status = 128 + number


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def host_command(command):
    """Allow executable shell entrypoints under Git Bash on Windows."""
    if os.name != "nt":
        return command
    executable = command[0]
    explicit = any(separator in executable for separator in ('/', '\\'))
    candidates = [Path(executable)] if explicit else [Path(directory) / executable for directory in os.get_exec_path()]
    for candidate in candidates:
        if candidate.is_file():
            if candidate.suffix.lower() in (".exe", ".com"):
                break
            with candidate.open("rb") as source:
                if source.read(2) == b"#!":
                    return [shutil.which("bash") or "bash", "-c", 'exec "$@"',
                            "android-lease-command", str(candidate), *command[1:]]
            break
        if candidate.with_name(candidate.name + ".exe").is_file():
            break
    return command


class Controller:
    def __init__(self, args):
        self.args = args
        self.path = args.lock_path
        self.record_path = self.path + "/lock.json"
        self.token_file = Path(args.token_file)
        self.adb_args = ["adb"] + (["-s", args.serial] if args.serial else [])

    def adb(self, *args, capture=False):
        return subprocess.run(host_command(self.adb_args + list(args)), env={**os.environ, "MSYS_NO_PATHCONV": "1"},
                              stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace")

    def shell(self, command, capture=False):
        return self.adb("shell", command, capture=capture)

    def connected(self):
        if self.adb("get-state").returncode:
            raise LeaseError("ADB device is unavailable")

    def read(self):
        try:
            result = self.shell("cat " + shlex.quote(self.record_path) + " 2>/dev/null", capture=True)
            if result.returncode:
                return None
            return metadata.decode(result.stdout)
        except (ValueError, TypeError):
            return None

    def remove(self):
        return self.shell("rm -rf " + shlex.quote(self.path)).returncode == 0

    @contextmanager
    def guard(self):
        guard = shlex.quote(self.path + ".guard")
        if self.shell("mkdir " + guard).returncode:
            raise LeaseError("Mutation guard busy; inspect ownership before retrying")
        try:
            yield
        finally:
            if self.shell("rmdir " + guard).returncode:
                raise LeaseError("Failed to remove mutation guard; inspect before recovery", 2)

    def publish(self, record):
        metadata.validate(record)
        template = Template(Path(__file__).with_name("lock.json.template").read_text(encoding="utf-8"))
        content = template.substitute({key: json.dumps(value, ensure_ascii=True) for key, value in record.items()})
        metadata.decode(content)
        with tempfile.TemporaryDirectory(prefix="android-lease-") as directory:
            source = Path(directory) / "lock.json"
            source.write_text(content, encoding="utf-8")
            if self.adb("push", str(source), self.record_path + ".tmp").returncode:
                raise LeaseError("Failed to upload lease metadata", 2)
            if self.shell("mv " + shlex.quote(self.record_path + ".tmp") + " " + shlex.quote(self.record_path)).returncode:
                raise LeaseError("Failed to publish lease metadata", 2)

    def acquire(self):
        self.connected()
        requested = utc_now()
        token = uuid.uuid4().hex
        deadline = time.monotonic() + self.args.wait_timeout_seconds
        while True:
            try:
                with self.guard():
                    if self.shell("mkdir " + shlex.quote(self.path)).returncode:
                        record = self.read()
                        if record is None or record["expires_at_epoch"] > int(time.time()):
                            raise LeaseError("Lease held or metadata unreadable")
                        if not self.remove() or self.shell("mkdir " + shlex.quote(self.path)).returncode:
                            raise LeaseError("Failed to replace expired lease", 2)
                    try:
                        # Persist recovery ownership before publishing; never lose the token
                        # when publication succeeds but a later cleanup fails.
                        self.token_file.write_text(token + "\n", encoding="utf-8")
                        self.publish(dict(project_dir=self.args.project_dir, test_name=self.args.test_name,
                                          requested_at_utc=requested, acquired_at_utc=utc_now(),
                                          max_timeout_seconds=self.args.max_timeout_seconds,
                                          expires_at_epoch=int(time.time()) + self.args.max_timeout_seconds,
                                          host=socket.gethostname(), pid=os.getpid(), adb_serial=self.args.serial,
                                          lock_path=self.path, owner_token=token))
                    except (OSError, LeaseError, Cancelled):
                        if self.remove():
                            self.token_file.unlink(missing_ok=True)
                        raise
                print("Acquired Android device lock", file=sys.stderr)
                return
            except LeaseError as error:
                if error.status != 1:
                    raise
                if time.monotonic() >= deadline:
                    raise LeaseError("Timed out waiting for Android device lock; inspect lease and mutation guard state") from error
                print("Waiting for Android device lock", file=sys.stderr)
                time.sleep(self.args.poll_seconds)

    def mutate(self, renew=False):
        with self.guard():
            self.connected()
            exists = self.shell("[ -e " + shlex.quote(self.path) + " ]").returncode == 0
            if not exists:
                if renew:
                    raise LeaseError("No Android device lock exists")
                return
            try:
                expected = self.token_file.read_text(encoding="utf-8").replace("\r", "").replace("\n", "")
            except OSError as error:
                raise LeaseError("Operation requires --token-file containing the owner token", 2) from error
            record = self.read()
            if record is None or record["owner_token"] != expected:
                raise LeaseError("Refusing mutation: owner token does not match")
            if renew:
                record.update(max_timeout_seconds=self.args.max_timeout_seconds,
                              expires_at_epoch=int(time.time()) + self.args.max_timeout_seconds,
                              adb_serial=self.args.serial, lock_path=self.path)
                self.publish(record)
                print("Renewed Android device lock", file=sys.stderr)
            else:
                if not self.remove():
                    raise LeaseError("Failed to delete Android device lock; owner token retained for recovery")
                self.token_file.unlink(missing_ok=True)
                print("Released Android device lock", file=sys.stderr)

    def run(self, command):
        self.acquire()
        status = 0
        tree = CommandTree()
        try:
            child = tree.start(host_command(command))
            while True:
                try:
                    status = child.wait(timeout=.2)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if status < 0:
                status = 128 - status
        except Cancelled as error:
            status = error.status
        except OSError:
            status = 127
        finally:
            with protected_cleanup():
                try:
                    tree.stop()
                except (OSError, subprocess.TimeoutExpired) as error:
                    print(f"Command tree cleanup failed; lease and owner token retained: {error}", file=sys.stderr)
                    status = status or 1
                else:
                    try:
                        self.mutate()
                    except (LeaseError, OSError) as error:
                        print(str(error), file=sys.stderr)
                        print("Release failed; owner token retained for recovery", file=sys.stderr)
                        status = status or 1
        return status


def cancellation_signals():
    return [signal.SIGINT, signal.SIGTERM] + ([signal.SIGBREAK] if hasattr(signal, "SIGBREAK") else [])


@contextmanager
def protected_cleanup():
    """Defer repeated cancellation until command and lease cleanup completes."""
    previous = {number: signal.getsignal(number) for number in cancellation_signals()}
    try:
        for number in previous:
            signal.signal(number, signal.SIG_IGN)
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("acquire", "release", "renew", "run"))
    for name, default in (("serial", ""), ("lock-path", "/data/local/tmp/android-device-test.lock.d"),
                          ("project-dir", os.getcwd()), ("test-name", "android-device-test"), ("token-file", None)):
        parser.add_argument("--" + name, default=default)
    for name, default in (("max-timeout-seconds", 1800), ("wait-timeout-seconds", 1800), ("poll-seconds", 5)):
        parser.add_argument("--" + name, type=int, default=default)
    argv = sys.argv[1:]
    split = argv.index("--") if "--" in argv else len(argv)
    args = parser.parse_args(argv[:split])
    command = argv[split + 1:]
    if not re.fullmatch(r"/data/local/tmp/[^/]+(?:/[^/]+)*", args.lock_path) or any(part in (".", "..") for part in args.lock_path.split("/")):
        parser.error("lock path must name a directory below /data/local/tmp without parent traversal")
    if args.max_timeout_seconds <= 0 or args.poll_seconds <= 0 or args.wait_timeout_seconds < 0:
        parser.error("invalid lease duration, wait timeout or poll interval")
    if args.mode == "run" and not command:
        parser.error("run requires a command after --")
    if args.token_file is None:
        descriptor, args.token_file = tempfile.mkstemp(prefix="android-lease-", suffix=".token")
        os.close(descriptor)
    def cancel(number, _frame):
        raise Cancelled(number)
    for number in cancellation_signals():
        signal.signal(number, cancel)
    controller = Controller(args)
    try:
        if args.mode == "run":
            return controller.run(command)
        if args.mode == "acquire":
            controller.acquire()
        else:
            controller.mutate(renew=args.mode == "renew")
        return 0
    except Cancelled as error:
        return error.status
    except (LeaseError, OSError) as error:
        print(str(error), file=sys.stderr)
        return error.status if isinstance(error, LeaseError) else 1


if __name__ == "__main__":
    sys.exit(main())
