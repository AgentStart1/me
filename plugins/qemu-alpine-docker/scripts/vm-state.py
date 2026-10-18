#!/usr/bin/env python3
"""VM lifecycle state owner; retain shell provisioning/guest command orchestration."""
import argparse
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import uuid

from process_identity import identity, windows_pid, write_record

spec = importlib.util.spec_from_file_location('qemu_control', Path(__file__).with_name('qemu-control.py'))
qemu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qemu)


class StateError(Exception):
    pass


class Cancelled(Exception):
    def __init__(self, number):
        self.status = 128 + number


def atomic_text(path, value):
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as output:
            output.write(str(value) + '\n')
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read(path):
    try:
        return path.read_text(encoding='utf-8').strip()
    except FileNotFoundError:
        return ''


def pid(value):
    return int(value) if re.fullmatch('[1-9][0-9]*', str(value)) else None


def running(value):
    number = pid(value)
    if number is None:
        return False
    native = windows_pid(number, strict=True) if os.name == 'nt' else number
    # Inspection errors propagate: unknown process state never authorizes mutation.
    return identity(native) is not None


class State:
    def __init__(self, args):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', args.name) or args.name in ('.', '..'):
            raise StateError('VM_NAME contains unsupported characters')
        self.name = args.name
        self.owner = args.owner
        self.native_owner = getattr(args, "native_owner", False)
        self.vms = Path(args.vm_dir)
        self.run_dir = Path(args.run_dir)
        self.active = Path(args.active_lock)
        self.guard_dir = Path(args.state_guard)
        self.operation = self.run_dir / 'vm-operation.lock'
        self.pid_path = self.vms / (self.name + '.pid')
        self.identity_path = self.vms / (self.name + '.qemu.json')

    def acquire_guard(self, owner=None):
        self.run_dir.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + 5
        while True:
            try:
                self.guard_dir.mkdir()
                break
            except FileExistsError:
                existing = read(self.guard_dir / 'owner.pid')
                if existing and not (identity(int(existing)) is not None if (self.guard_dir / 'native-owner').exists() else running(existing)):
                    raise StateError('stale VM state guard; inspect before manual recovery')
                if time.monotonic() >= deadline:
                    raise StateError('timed out waiting for the VM state guard')
                time.sleep(.05)
        token = uuid.uuid4().hex
        try:
            atomic_text(self.guard_dir / 'owner.pid', owner or os.getpid())
            if owner is None:
                atomic_text(self.guard_dir / 'native-owner', 'true')
            atomic_text(self.guard_dir / 'token', token)
        except (OSError, Cancelled):
            # An incomplete guard remains unknown; never recover it by age.
            raise
        return token

    def release_guard(self, token):
        if read(self.guard_dir / 'token') != token:
            raise StateError('VM state guard ownership changed; refusing cleanup')
        for name in ('owner.pid', 'token', 'native-owner'):
            (self.guard_dir / name).unlink(missing_ok=True)
        self.guard_dir.rmdir()

    @contextmanager
    def guarded(self):
        token = self.acquire_guard()
        try:
            yield
        finally:
            previous = {number: signal.signal(number, signal.SIG_IGN) for number in signals()}
            try:
                self.release_guard(token)
            finally:
                for number, handler in previous.items():
                    signal.signal(number, handler)

    def begin(self, token):
        with self.guarded():
            try:
                self.operation.mkdir()
            except FileExistsError as error:
                raise StateError('VM lifecycle operation is busy or interrupted; inspect vm-operation.lock before recovery') from error
            atomic_text(self.operation / 'owner.pid', self.owner)
            atomic_text(self.operation / 'token', token)
            atomic_text(self.operation / 'vm-name', self.name)

    def end(self, token):
        with self.guarded():
            if not self.operation.exists():
                return
            if read(self.operation / 'owner.pid') == str(self.owner) and read(self.operation / 'token') == token:
                for name in ('owner.pid', 'token', 'vm-name'):
                    (self.operation / name).unlink(missing_ok=True)
                self.operation.rmdir()

    def acquire(self):
        with self.guarded():
            if self.active.exists():
                name = read(self.active / 'vm-name')
                if not name or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]*', name):
                    raise StateError('Unknown VM lock metadata; inspect before recovery')
                if name and (self.vms / (name + '.gvproxy.pid')).exists():
                    raise StateError(f"VM '{name}' retains gvproxy state; stop that VM before another launch")
                if running(read(self.active / 'qemu.pid')) or self.launcher_running():
                    raise StateError(f"VM '{name or 'unknown'}' already owns the global lock")
                self.remove_active()
            self.active.mkdir()
            atomic_text(self.active / 'vm-name', self.name)
            atomic_text(self.active / 'launcher.pid', self.owner)
            if self.native_owner:
                atomic_text(self.active / 'launcher-native', 'true')

    def launcher_running(self):
        value = read(self.active / 'launcher.pid')
        if (self.active / 'launcher-native').exists():
            number = pid(value)
            return number is not None and identity(number) is not None
        return running(value)

    def qemu_running(self):
        number = pid(read(self.pid_path))
        if number is None:
            return False
        if self.identity_path.exists():
            record = json.loads(self.identity_path.read_text())
            return record.get('shell_pid') == number and identity(record['pid']) == record['identity']
        return qemu.probe(number, self.name) is not None

    def remove_active(self):
        for name in ('qemu.pid', 'launcher.pid', 'vm-name', 'launcher-native', 'launch.pid'):
            (self.active / name).unlink(missing_ok=True)
        self.active.rmdir()

    def release(self):
        with self.guarded():
            if not self.active.exists():
                return
            if read(self.active / 'vm-name') != self.name:
                raise StateError('Refusing to release another VM reservation')
            if (self.vms / (self.name + '.gvproxy.pid')).exists():
                raise StateError('gvproxy state remains; retaining VM reservation')
            if running(read(self.active / 'qemu.pid')):
                raise StateError('QEMU process remains; retaining VM reservation')
            launcher = read(self.active / 'launcher.pid')
            if launcher != str(self.owner) and self.launcher_running():
                raise StateError('Another launcher owns the VM reservation')
            self.remove_active()

    def register(self, number):
        with self.guarded():
            if read(self.active / 'vm-name') != self.name or read(self.active / 'launcher.pid') != str(self.owner):
                raise StateError('Cannot register QEMU without owning the VM reservation')
            record = qemu.probe(number, self.name)
            if record is None:
                raise StateError('Cannot register a missing or unrelated QEMU process; retaining state for inspection')
            # Publish identity before PID pointers. Partial writes remain reserved.
            write_record(self.identity_path, record)
            atomic_text(self.pid_path, number)
            atomic_text(self.active / 'qemu.pid', number)

    def clear(self, keep=False):
        with self.guarded():
            if self.qemu_running():
                raise StateError('QEMU process remains; retaining VM state')
            if (self.vms / (self.name + '.gvproxy.pid')).exists():
                raise StateError('gvproxy state remains; retaining VM reservation')
            active_pid = read(self.active / 'qemu.pid')
            recorded = json.loads(self.identity_path.read_text()) if self.identity_path.exists() else None
            confirmed_exit = recorded is not None and str(recorded.get('shell_pid')) == active_pid
            self.pid_path.unlink(missing_ok=True)
            self.identity_path.unlink(missing_ok=True)
            if read(self.active / 'vm-name') != self.name:
                return
            if not confirmed_exit and running(active_pid):
                return
            (self.active / 'qemu.pid').unlink(missing_ok=True)
            if keep:
                return
            launcher = read(self.active / 'launcher.pid')
            if launcher == str(self.owner) or not self.launcher_running():
                self.remove_active()


def signals():
    return [signal.SIGINT, signal.SIGTERM] + ([signal.SIGBREAK] if hasattr(signal, 'SIGBREAK') else [])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('begin', 'end', 'acquire', 'release', 'register', 'clear', 'guard-acquire', 'guard-release'))
    for name in ('vm-dir', 'run-dir', 'active-lock', 'state-guard', 'name'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--owner', type=int, required=True)
    parser.add_argument('--pid', type=int)
    parser.add_argument('--token', default='')
    parser.add_argument('--keep-lock', action='store_true')
    args = parser.parse_args()
    def cancel(number, _frame):
        raise Cancelled(number)
    for number in signals():
        signal.signal(number, cancel)
    try:
        state = State(args)
        if args.action == 'begin':
            token = args.token or uuid.uuid4().hex
            state.begin(token)
            print(token)
        elif args.action == 'end':
            state.end(args.token)
        elif args.action == 'guard-acquire':
            print(state.acquire_guard(args.owner))
        elif args.action == 'guard-release':
            state.release_guard(args.token)
        elif args.action == 'register':
            if not args.pid or args.pid <= 0:
                parser.error('register requires a positive --pid')
            state.register(args.pid)
        elif args.action == 'clear':
            state.clear(args.keep_lock)
        else:
            getattr(state, args.action)()
        return 0
    except Cancelled as error:
        return error.status
    except (OSError, ValueError, RuntimeError, StateError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
