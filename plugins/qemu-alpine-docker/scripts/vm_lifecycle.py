#!/usr/bin/env python3
"""Python start/stop lifecycle; shell adapters retain SDK/platform and guest commands."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
import uuid

from process_identity import identity, terminate

spec = importlib.util.spec_from_file_location('vm_state', Path(__file__).with_name('vm-state.py'))
state_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(state_module)

FAILURES = (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError, state_module.StateError)


class Lifecycle:
    def __init__(self, profile):
        self.profile = str(Path(profile).resolve())
        self.bash = os.environ.get('QEMU_BASH_BINARY') or shutil.which('bash')
        if not self.bash:
            raise state_module.StateError('Bash is required for platform and guest command adapters')
        self.adapter = Path(__file__).with_name('vm-lifecycle-step.sh')
        self.child = None
        self.reserved = False
        self.started = False
        self.args = SimpleNamespace(**json.loads(self.step('describe', capture=True)), owner=os.getpid(), native_owner=True)
        if os.name == 'nt':
            os.environ['QEMU_MSYS_PS_BIN'] = self.args.msys_ps
        self.state = state_module.State(self.args)
        self.home = self.state.vms / self.state.name
        self.token = uuid.uuid4().hex

    def step(self, action, *args, capture=False, optional=False):
        command = [self.bash, str(self.adapter), self.profile, action, *map(str, args)]
        child = subprocess.Popen(command, stdout=subprocess.PIPE if capture else None,
                                 start_new_session=os.name != 'nt')
        try:
            while True:
                try:
                    output, _ = child.communicate(timeout=.2)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if child.returncode and not optional:
                raise state_module.StateError('VM adapter failed: ' + action)
            return output.decode('utf-8') if capture else child.returncode
        except state_module.Cancelled:
            # Signal only this live adapter. QEMU/gvproxy are cleaned by their
            # persisted process identities at the lifecycle boundary below.
            if child.poll() is None:
                if os.name == 'nt':
                    child.terminate()
                else:
                    os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            raise

    def record(self):
        number = state_module.pid(state_module.read(self.state.pid_path))
        if number is None:
            return None
        if self.state.identity_path.exists():
            record = json.loads(self.state.identity_path.read_text())
            if record.get('shell_pid') != number:
                return None
            return record if identity(record['pid']) == record['identity'] else None
        return state_module.qemu.probe(number, self.state.name)

    def wait_ready(self):
        timeout = int(os.environ.get('BOOT_TIMEOUT', '300'))
        self.wait_probe('ssh-ready', timeout)
        self.wait_probe('docker-ready', 120)
        self.step('pool-ready')

    def wait_probe(self, action, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.record() is None:
                raise state_module.StateError('QEMU exited before readiness')
            if self.step(action, optional=True) == 0:
                return
            time.sleep(min(2, max(0, deadline - time.monotonic())))
        raise state_module.StateError('Timed out waiting for ' + action)

    def stop_owned(self):
        record = self.record()
        pending = self.state.active / 'launch.pid'
        if record is None and pending.exists():
            number = state_module.pid(state_module.read(pending))
            stored = json.loads(self.state.identity_path.read_text()) if self.state.identity_path.exists() else None
            if stored and stored.get('shell_pid') == number:
                record = stored if identity(stored['pid']) == stored['identity'] else None
            elif number:
                record = state_module.qemu.probe(number, self.state.name)
                if record is None and state_module.running(number):
                    raise state_module.StateError('Unknown launched process; retaining VM ownership')
        if record is None and self.child is not None and self.child.poll() is None and not pending.exists():
            raise state_module.StateError('Launch PID publication incomplete; inspect before recovery')
        if record is not None:
            terminate(record)
        if self.record() is not None:
            raise state_module.StateError('QEMU remains; retaining VM ownership')
        self.step('network-stop')
        self.state.clear()

    def start(self):
        if not (self.home / 'disk.qcow2').is_file():
            raise state_module.StateError('VM disk not found. Run create-vm.sh first.')
        if not (self.home / 'ready').is_file():
            raise state_module.StateError('VM has not passed provisioning verification')
        if self.record() is not None:
            self.step('network-check')
            self.wait_ready()
            print('VM is already running', file=sys.stderr)
            self.started = True
            return
        plan = json.loads(self.step('plan', capture=True))
        self.state.acquire()
        self.reserved = True
        self.step('network-start')
        pid_file = self.state.active / 'launch.pid'
        with (self.home / 'qemu.log').open('ab') as log:
            self.child = subprocess.Popen([self.bash, str(self.adapter), self.profile, 'launch', str(pid_file), *plan],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=os.name != 'nt')
        deadline = time.monotonic() + 10
        while not pid_file.exists():
            if self.child.poll() is not None or time.monotonic() >= deadline:
                raise state_module.StateError('QEMU launch adapter failed before PID publication')
            time.sleep(.05)
        number = state_module.pid(pid_file.read_text().strip())
        if number is None:
            raise state_module.StateError('Invalid launched QEMU PID')
        # Register before readiness. Windows records the shell/native PID
        # mapping through the original launching Bash runtime.
        self.state.register(number)
        self.wait_ready()
        self.started = True
        print('VM is ready in the background', file=sys.stderr)

    def stop(self):
        name = state_module.read(self.state.active / 'vm-name')
        if name == self.state.name and self.state.launcher_running():
            raise state_module.StateError('VM launch/provisioning is in progress; its owner must finish or cancel it before shutdown')
        if self.record() is None:
            self.step('network-stop')
            self.state.clear()
            return
        if os.environ.get('FORCE', 'false') != 'true':
            self.step('poweroff', optional=True)
            deadline = time.monotonic() + int(os.environ.get('TIMEOUT', '30'))
            while self.record() is not None and time.monotonic() < deadline:
                time.sleep(.2)
        self.stop_owned()
        print('VM stopped', file=sys.stderr)

    def execute(self, action):
        self.state.begin(self.token)
        status = 0
        try:
            getattr(self, action)()
        except state_module.Cancelled as error:
            status = error.status
        except FAILURES as error:
            print('Error: ' + str(error), file=sys.stderr)
            status = 1
        finally:
            for number in state_module.signals():
                signal.signal(number, signal.SIG_IGN)
            if action == 'start' and self.reserved and not self.started:
                try:
                    self.stop_owned()
                except FAILURES as error:
                    print('Cleanup failed; retaining VM reservation: ' + str(error), file=sys.stderr)
                    status = status or 1
            try:
                self.state.end(self.token)
            except (OSError, state_module.StateError) as error:
                print('Operation cleanup failed: ' + str(error), file=sys.stderr)
                status = status or 1
        return status


def main(action=None):
    parser = argparse.ArgumentParser(description=__doc__)
    if action is None:
        parser.add_argument('action', choices=('start', 'stop'))
    parser.add_argument('profile', nargs='?', default=str(Path(__file__).resolve().parents[1] / 'profiles/dev.profile'))
    args = parser.parse_args()
    def cancel(number, _frame):
        raise state_module.Cancelled(number)
    for number in state_module.signals():
        signal.signal(number, cancel)
    try:
        return Lifecycle(args.profile).execute(action or args.action)
    except state_module.Cancelled as error:
        return error.status
    except FAILURES as error:
        print('Error: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
