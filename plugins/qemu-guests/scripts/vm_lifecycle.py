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

from process_identity import terminate
from vm_phase import Phase, NoProcess, UnknownProcess, NativeUnknownProcess

spec = importlib.util.spec_from_file_location('vm_state', Path(__file__).with_name('vm-state.py'))
state_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(state_module)

FAILURES = (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError, state_module.StateError)
defer_cancellation = state_module.defer_cancellation


class Lifecycle:
    def __init__(self, profile):
        self.profile = str(Path(profile).resolve())
        self.bash = os.environ.get('QEMU_BASH_BINARY') or shutil.which('bash')
        if not self.bash:
            raise state_module.StateError('Bash is required for platform and guest command adapters')
        self.adapter = Path(__file__).with_name('vm-lifecycle-step.sh')
        self.child = None
        self.pending_controller = None
        self.owned = None  # A snapshot only for reservations acquired by this operation.
        self.args = SimpleNamespace(**json.loads(self.step('describe', capture=True)), owner=os.getpid(), native_owner=True)
        if os.name == 'nt':
            os.environ['QEMU_MSYS_PS_BIN'] = self.args.msys_ps
        self.state = state_module.State(self.args)
        self.home = self.state.vms / self.state.name
        self.token = uuid.uuid4().hex

    def step(self, action, *args, capture=False, optional=False):
        command = [self.bash, str(self.adapter), self.profile, action, *map(str, args)]
        return self.run_child(command, action, capture=capture, optional=optional)

    def run_child(self, command, action, capture=False, optional=False, data=None, native=False):
        child = None
        try:
            with defer_cancellation():
                child = subprocess.Popen(command, stdout=subprocess.PIPE if capture else None,
                    stdin=subprocess.PIPE if data is not None else None, start_new_session=os.name != 'nt',
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' and native else 0)
                if native:
                    self.pending_controller = child
            while True:
                try:
                    output, _ = child.communicate(input=data, timeout=.2)
                    break
                except subprocess.TimeoutExpired:
                    data = None
                    continue
            if child.returncode and not optional:
                raise state_module.StateError('VM adapter failed: ' + action)
            return output.decode('utf-8') if capture else child.returncode
        except state_module.Cancelled:
            # Signal only this live adapter. QEMU/gvproxy are cleaned by their
            # persisted process identities at the lifecycle boundary below.
            try:
                if child is not None and child.poll() is None:
                    try:
                        if os.name == 'nt':
                            if native:
                                child.send_signal(signal.CTRL_BREAK_EVENT)
                            else:
                                child.terminate()
                        else:
                            os.killpg(child.pid, signal.SIGTERM)
                    except OSError:
                        # A failed graceful signal still requires a joined child.
                        if child.poll() is None:
                            child.kill()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=5)
            except (OSError, subprocess.SubprocessError) as error:
                print('Controller cancellation failed; retaining ownership: ' + str(error), file=sys.stderr)
            raise
        finally:
            if native and child is not None and child.poll() is not None:
                self.pending_controller = None

    def network(self, action):
        """Own the native controller until exit, so cancellation cannot publish late state."""
        plan = json.loads(self.step('network-plan', action, capture=True))
        path = Path(plan['state'])
        if action == 'stop' and not path.exists():
            if Path(str(path) + '.control.lock').exists():
                raise state_module.StateError('gvproxy controller remains; retaining VM ownership')
            return
        command = [sys.executable, str(Path(__file__).with_name('gvproxy-control.py')), action,
                   '--state', plan['state'], '--api', plan['api'], '--transport', plan['transport']]
        if action == 'start':
            command.extend(('--configure', '--binary', plan['binary'], '--log', plan['log']))
        self.run_child(command, 'network-' + action, data=plan['mappings'].encode() if action != 'stop' else None, native=True)

    def transition(self, phase, process=None):
        self.owned = self.state.transition(self.owned.generation, phase, process)

    def begin_stop(self, record=None):
        self.state.mark_stopping(record)

    def record(self):
        return self.state.process_record()

    def wait_ready(self):
        timeout = int(self.args.boot_timeout)
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
        controller = self.pending_controller
        if controller is not None:
            if controller.poll() is None:
                raise state_module.StateError('Native network controller remains; retaining operation lease')
            controller.wait(timeout=5)
            self.pending_controller = None
        snapshot = self.state.snapshot() if state_module.read(self.state.active / 'vm-name') == self.state.name else None
        if self.owned is not None and (snapshot is None or snapshot.generation != self.owned.generation):
            raise state_module.StateError('VM reservation changed; refusing obsolete cleanup')
        if snapshot is not None and isinstance(snapshot.process, UnknownProcess) and self.child is not None:
            # This controller owns the native Popen handle; no shell handoff is needed.
            state_module.write_record(self.state.active / 'launch.pid', {'kind': 'native', 'pid': self.child.pid})
        record = self.record()
        self.begin_stop(record)
        if record is not None:
            terminate(record)
        if self.record() is not None:
            raise state_module.StateError('QEMU remains; retaining VM ownership')
        if self.child is not None:
            self.child.wait(timeout=5)
        self.network('stop')
        self.state.clear()

    def start(self):
        if not (self.home / 'disk.qcow2').is_file():
            raise state_module.StateError('VM disk not found. Run create-vm.sh first.')
        if not (self.home / 'ready').is_file():
            raise state_module.StateError('VM has not passed provisioning verification')
        if self.record() is not None:
            self.network('check')
            self.wait_ready()
            print('VM is already running', file=sys.stderr)
            return
        plan = json.loads(self.step('plan', capture=True))
        with defer_cancellation():
            self.owned = self.state.acquire()
        self.transition(Phase.NETWORK_STARTING)
        self.network('start')
        self.transition(Phase.NETWORK_READY)
        # Plans contain native executable paths and argv, never shell commands.
        with (self.home / 'qemu.log').open('ab') as log:
            with defer_cancellation():
                self.transition(Phase.SPAWNING, NativeUnknownProcess())
                try:
                    self.child = subprocess.Popen(plan, stdin=subprocess.DEVNULL,
                        stdout=log, stderr=log, start_new_session=os.name != 'nt',
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
                except OSError:
                    self.transition(Phase.NETWORK_READY, NoProcess())
                    raise
                state_module.write_record(self.state.active / 'launch.pid', {'kind': 'native', 'pid': self.child.pid})
        self.owned = self.state.register(self.child.pid, native=True)
        self.wait_ready()
        with defer_cancellation():
            self.transition(Phase.READY)
        print('VM is ready in the background', file=sys.stderr)

    def stop(self):
        name = state_module.read(self.state.active / 'vm-name')
        if name == self.state.name and self.state.launcher_running():
            raise state_module.StateError('VM launch/provisioning is in progress; its owner must finish or cancel it before shutdown')
        record = self.record()
        if record is None:
            self.stop_owned()
            return
        self.begin_stop(record)
        if self.args.force != 'true':
            self.step('poweroff', optional=True)
            deadline = time.monotonic() + int(self.args.stop_timeout)
            while self.record() is not None and time.monotonic() < deadline:
                time.sleep(.2)
        self.stop_owned()
        print('VM stopped', file=sys.stderr)

    def execute(self, action):
        lease_owned = False
        status = 0
        try:
            with defer_cancellation():
                self.state.begin(self.token)
                lease_owned = True
            getattr(self, action)()
        except state_module.Cancelled as error:
            status = error.status
        except FAILURES as error:
            print('Error: ' + str(error), file=sys.stderr)
            status = 1
        finally:
            previous = {number: signal.signal(number, signal.SIG_IGN) for number in state_module.signals()}
            if lease_owned and action == 'start' and self.owned is not None and self.owned.phase != Phase.READY:
                try:
                    self.stop_owned()
                except FAILURES as error:
                    try:
                        self.state.transition(self.owned.generation, Phase.RECOVERY)
                    except FAILURES:
                        pass  # Preserve the last durable evidence if even publication fails.
                    print('Cleanup failed; retaining VM reservation: ' + str(error), file=sys.stderr)
                    status = status or 1
            try:
                if lease_owned and (self.pending_controller is None or self.pending_controller.poll() is not None):
                    self.state.end(self.token)
                elif lease_owned:
                    print('Operation lease retained: native network controller exit is unconfirmed', file=sys.stderr)
            except (OSError, state_module.StateError) as error:
                print('Operation cleanup failed: ' + str(error), file=sys.stderr)
                status = status or 1
            finally:
                for number, handler in previous.items():
                    signal.signal(number, handler)
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
