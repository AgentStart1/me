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

from process_identity import identity, windows_pid, write_record, terminate
from resource_ownership import Cancelled, defer_cancellation, signals
from vm_phase import Phase, Snapshot, NoProcess, UnknownProcess, LaunchedProcess, OwnedProcess, NativeUnknownProcess, NativeLaunchedProcess

spec = importlib.util.spec_from_file_location('qemu_control', Path(__file__).with_name('qemu-control.py'))
qemu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qemu)


class StateError(Exception):
    pass


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
        self.snapshot_path = self.active / 'lifecycle.json'

    def snapshot(self):
        if not self.snapshot_path.exists():
            return None  # Pre-controller reservations are resolved by their legacy records.
        return Snapshot.from_data(json.loads(self.snapshot_path.read_text()))

    def network_retained(self, name=None):
        path = self.vms / ((name or self.name) + '.gvproxy.pid')
        return path.exists() or Path(str(path) + '.control.lock').exists()

    def transition(self, generation, phase, process=None):
        with self.guarded():
            if read(self.active / 'vm-name') != self.name:
                raise StateError('Another VM owns the lifecycle state')
            current = self.snapshot()
            if current is None or current.generation != generation:
                raise StateError('VM reservation generation changed; refusing late publication')
            updated = current.transition(phase, process)
            write_record(self.snapshot_path, updated.data())
            return updated

    def acquire_guard(self, owner=None, token=None):
        self.run_dir.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + 5
        owned = False
        try:
            with defer_cancellation():
                while True:
                    try:
                        self.guard_dir.mkdir()
                        owned = True
                        break
                    except FileExistsError:
                        existing = read(self.guard_dir / 'owner.pid')
                        if existing and not (identity(int(existing)) is not None if (self.guard_dir / 'native-owner').exists() else running(existing)):
                            raise StateError('stale VM state guard; inspect before manual recovery')
                        if time.monotonic() >= deadline:
                            raise StateError('timed out waiting for the VM state guard')
                        time.sleep(.05)
                token = token or uuid.uuid4().hex
                atomic_text(self.guard_dir / 'owner.pid', owner or os.getpid())
                if owner is None:
                    atomic_text(self.guard_dir / 'native-owner', 'true')
                atomic_text(self.guard_dir / 'token', token)
        except BaseException:
            # mkdir succeeded in this call, and no guarded side effect ran.
            # Roll back only our new guard; pre-existing guards remain unknown.
            if owned:
                with defer_cancellation():
                    self.remove_guard()
            raise
        return token

    def release_guard(self, token):
        if read(self.guard_dir / 'token') != token:
            raise StateError('VM state guard ownership changed; refusing cleanup')
        self.remove_guard()

    def end_guard(self, token):
        """Idempotent rollback for a caller's known token, including failed claims."""
        with defer_cancellation():
            if (not token or read(self.guard_dir / 'token') != token or
                    read(self.guard_dir / 'owner.pid') != str(self.owner)):
                return
            self.release_guard(token)

    def remove_guard(self):
        for name in ('owner.pid', 'token', 'native-owner'):
            (self.guard_dir / name).unlink(missing_ok=True)
        self.guard_dir.rmdir()

    @contextmanager
    def guarded(self):
        # Mutations include directory teardown and compatibility pointers, not
        # just the atomic snapshot. Finish this bounded critical section before
        # delivering a handled signal; readiness/network IO never runs here.
        with defer_cancellation():
            token = self.acquire_guard()
            try:
                yield
            finally:
                self.release_guard(token)

    def begin(self, token):
        with self.guarded():
            try:
                self.operation.mkdir()
            except FileExistsError as error:
                raise StateError('VM lifecycle operation is busy or interrupted; inspect vm-operation.lock before recovery') from error
            try:
                atomic_text(self.operation / 'owner.pid', self.owner)
                atomic_text(self.operation / 'token', token)
                atomic_text(self.operation / 'vm-name', self.name)
            except (OSError, Cancelled):
                # Only this newly created directory is owned; never recover an
                # existing/interrupted lease. No operation side effects ran yet.
                self.remove_operation()
                raise

    def remove_operation(self):
        for name in ('owner.pid', 'token', 'vm-name'):
            (self.operation / name).unlink(missing_ok=True)
        self.operation.rmdir()

    def end(self, token):
        with self.guarded():
            if not self.operation.exists():
                return
            if read(self.operation / 'owner.pid') == str(self.owner) and read(self.operation / 'token') == token:
                self.remove_operation()

    def acquire(self):
        with self.guarded():
            if self.network_retained():
                raise StateError('Existing gvproxy ownership; stop that VM before another launch')
            if self.qemu_running():
                raise StateError('QEMU already owns this VM; refusing another launch')
            if self.active.exists():
                name = read(self.active / 'vm-name')
                if not name or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]*', name):
                    raise StateError('Unknown VM lock metadata; inspect before recovery')
                if self.network_retained(name):
                    raise StateError(f"VM '{name}' retains gvproxy state; stop that VM before another launch")
                if self.process_record(name) is not None or self.launcher_running():
                    raise StateError(f"VM '{name or 'unknown'}' already owns the global lock")
                self.remove_active()
            self.active.mkdir()
            try:
                atomic_text(self.active / 'vm-name', self.name)
                atomic_text(self.active / 'launcher.pid', self.owner)
                if self.native_owner:
                    atomic_text(self.active / 'launcher-native', 'true')
                snapshot = Snapshot(uuid.uuid4().hex, Phase.RESERVED, NoProcess())
                write_record(self.snapshot_path, snapshot.data())
                # Old compatibility pointers were proven stale before acquisition.
                # Remove them before QEMU can exist in the new reservation.
                self.pid_path.unlink(missing_ok=True)
                self.identity_path.unlink(missing_ok=True)
                return snapshot
            except (OSError, Cancelled):
                # A failed reservation publication has not launched any process.
                self.remove_active()
                raise

    def launcher_running(self):
        value = read(self.active / 'launcher.pid')
        if (self.active / 'launcher-native').exists():
            number = pid(value)
            return number is not None and identity(number) is not None
        return running(value)

    def process_record(self, name=None):
        """Resolve partial publication; missing PID pointers do not prove exit."""
        name = name or self.name
        pointers = [self.vms / (name + '.pid')]
        snapshot = None
        pending = None
        native = False
        if read(self.active / 'vm-name') == name:
            snapshot = self.snapshot()
            pending = self.active / 'launch.pid'
            if (self.active / 'launch-pending').exists() and not pending.exists():
                raise StateError('Launch PID publication incomplete; inspect before recovery')
            pointers.extend((self.active / 'qemu.pid', pending))
        numbers = set()
        for path in pointers:
            if path.exists():
                content = read(path)
                if path == pending and content.startswith('{'):
                    launch = json.loads(content)
                    if not isinstance(launch, dict) or launch.get('kind') != 'native':
                        raise StateError('Invalid native launch evidence')
                    if type(launch.get('pid')) is not int:
                        raise StateError('Invalid native launch PID type')
                    number = pid(launch['pid'])
                    native = True
                else:
                    number = pid(content)
                if number is None:
                    raise StateError('Invalid QEMU PID state; inspect before recovery')
                numbers.add(number)
        evidence = snapshot.process if snapshot else NoProcess()
        if isinstance(evidence, LaunchedProcess):
            numbers.add(evidence.shell_pid)
        identity_path = self.vms / (name + '.qemu.json')
        record = json.loads(identity_path.read_text()) if identity_path.exists() else None
        if isinstance(evidence, OwnedProcess):
            if record is not None and record != evidence.record():
                raise StateError('Conflicting QEMU identity state; inspect before recovery')
            record = evidence.record()
        if record is not None:
            number = pid(record['shell_pid'])
            if number is None or numbers - {number}:
                raise StateError('Conflicting QEMU PID state; inspect before recovery')
            return record if identity(record['pid']) == record['identity'] else None
        if len(numbers) > 1:
            raise StateError('Conflicting QEMU PID state; inspect before recovery')
        if not numbers:
            if isinstance(evidence, UnknownProcess):
                raise StateError('Launch PID publication incomplete; inspect before recovery')
            return None
        number = numbers.pop()
        native = native or isinstance(evidence, (NativeUnknownProcess, NativeLaunchedProcess))
        record = qemu.probe(number, name, native_pid=True) if native else qemu.probe(number, name)
        if record is None and (identity(number) is not None if native else running(number)):
            raise StateError('Unknown launched process; retaining VM ownership')
        return record

    def qemu_running(self):
        return self.process_record() is not None

    def prepare_launch(self):
        if read(self.active / 'launcher.pid') != str(self.owner):
            raise StateError('Cannot launch QEMU without owning the VM reservation')
        current = self.snapshot()
        if current is None:
            raise StateError('Cannot launch without a lifecycle snapshot')
        return self.transition(current.generation, Phase.SPAWNING, UnknownProcess())

    def remove_active(self):
        for name in ('qemu.pid', 'launcher.pid', 'vm-name', 'launcher-native', 'launch.pid', 'launch-pending', 'lifecycle.json'):
            (self.active / name).unlink(missing_ok=True)
        self.active.rmdir()

    def release(self):
        with self.guarded():
            if not self.active.exists():
                return
            if read(self.active / 'vm-name') != self.name:
                raise StateError('Refusing to release another VM reservation')
            if self.network_retained():
                raise StateError('gvproxy state remains; retaining VM reservation')
            if self.qemu_running():
                raise StateError('QEMU process remains; retaining VM reservation')
            launcher = read(self.active / 'launcher.pid')
            if launcher != str(self.owner) and self.launcher_running():
                raise StateError('Another launcher owns the VM reservation')
            self.remove_active()

    def register(self, number, *, native=False):
        with self.guarded():
            if read(self.active / 'vm-name') != self.name or read(self.active / 'launcher.pid') != str(self.owner):
                raise StateError('Cannot register QEMU without owning the VM reservation')
            current = self.snapshot()
            native = native or (current is not None and isinstance(current.process, (NativeUnknownProcess, NativeLaunchedProcess)))
            launched = NativeLaunchedProcess(number) if native else LaunchedProcess(number)
            if current is None:
                current = Snapshot(uuid.uuid4().hex, Phase.LAUNCHED, launched)
            elif current.phase != Phase.LAUNCHED and not (
                    current.phase == Phase.REGISTERED and current.process.shell_pid == number):
                current = current.transition(Phase.LAUNCHED, launched)
            if current.process.shell_pid != number:
                raise StateError('Registered PID differs from the launched process')
            # Persist launch evidence before inspection, then the native identity
            # before compatibility files. Each interrupted prefix remains recoverable.
            write_record(self.snapshot_path, current.data())
            record = qemu.probe(number, self.name, native_pid=True) if native else qemu.probe(number, self.name)
            if record is None:
                raise StateError('Cannot register a missing or unrelated QEMU process; retaining state for inspection')
            if current.phase != Phase.REGISTERED:
                current = current.transition(Phase.REGISTERED, OwnedProcess.from_record(record))
                write_record(self.snapshot_path, current.data())
            elif current.process.record() != record:
                raise StateError('Registered process identity changed; refusing replacement')
            write_record(self.identity_path, record)
            atomic_text(self.pid_path, number)
            atomic_text(self.active / 'qemu.pid', number)
            return current

    def stop_qemu(self):
        record = self.process_record()
        self.mark_stopping(record)
        if record is not None:
            terminate(record)
        if self.process_record() is not None:
            raise StateError('QEMU remains; retaining VM ownership')

    def mark_stopping(self, record=None):
        if read(self.active / 'vm-name') != self.name:
            return
        snapshot = self.snapshot()
        if snapshot is not None and (snapshot.phase != Phase.STOPPING or
                record is not None and not isinstance(snapshot.process, OwnedProcess)):
            self.transition(snapshot.generation, Phase.STOPPING,
                OwnedProcess.from_record(record) if record is not None else None)

    def clear(self, keep=False):
        with self.guarded():
            if self.qemu_running():
                raise StateError('QEMU process remains; retaining VM state')
            if self.network_retained():
                raise StateError('gvproxy state remains; retaining VM reservation')
            owns_active = read(self.active / 'vm-name') == self.name
            release_active = owns_active and not keep and (
                read(self.active / 'launcher.pid') == str(self.owner) or not self.launcher_running())
            self.pid_path.unlink(missing_ok=True)
            self.identity_path.unlink(missing_ok=True)
            if not owns_active:
                return
            for name in ('qemu.pid', 'launch.pid', 'launch-pending'):
                (self.active / name).unlink(missing_ok=True)
            if release_active:
                self.remove_active()
            elif keep:
                current = self.snapshot()
                if current is not None:
                    if current.phase != Phase.STOPPING:
                        current = current.transition(Phase.STOPPING)
                    write_record(self.snapshot_path, current.transition(Phase.RESERVED, NoProcess()).data())


def publish_claim(state, action, token):
    """Creator owns rollback until output succeeds; the caller already knows token.

    Shell callers must install token-checked cleanup before requesting creation,
    and join the creator before rollback, so cancellation cannot publish late state.
    """
    owned = False
    try:
        with defer_cancellation():
            if action == 'begin':
                state.begin(token)
            else:
                state.acquire_guard(state.owner, token)
            owned = True
        print(token, flush=True)
    except BaseException:
        if owned:
            with defer_cancellation():
                if action == 'begin':
                    state.end(token)
                else:
                    state.end_guard(token)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('new-token', 'begin', 'end', 'acquire', 'release', 'register', 'clear', 'prepare_launch', 'stop_qemu', 'guard-acquire', 'guard-release'))
    for name in ('vm-dir', 'run-dir', 'active-lock', 'state-guard', 'name'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--owner', type=int, required=True)
    parser.add_argument('--pid', type=int)
    parser.add_argument('--token', default='')
    parser.add_argument('--keep-lock', action='store_true')
    args = parser.parse_args()
    if args.action in ('begin', 'guard-acquire') and not args.token:
        parser.error('claim requires a caller-generated --token and preinstalled cleanup')
    def cancel(number, _frame):
        raise Cancelled(number)
    for number in signals():
        signal.signal(number, cancel)
    try:
        state = State(args)
        if args.action == 'new-token':
            print(uuid.uuid4().hex, flush=True)
        elif args.action in ('begin', 'guard-acquire'):
            publish_claim(state, args.action, args.token)
        elif args.action == 'end':
            state.end(args.token)
        elif args.action == 'guard-release':
            state.end_guard(args.token)
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
