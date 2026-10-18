"""Deterministic CLI/Shell ownership handoffs using private state and real Bash."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]

# Instrument only the fixture's interpreter entrypoint, never production code.
INTERPRETER = r'''
import builtins, importlib.util, os, signal, sys, time
from pathlib import Path
script = Path(sys.argv[1])
sys.path.insert(0, str(script.parent))
sys.argv = sys.argv[1:]
spec = importlib.util.spec_from_file_location('fixture_state', script)
state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(state)
action = sys.argv[1]
claim = action in ('begin', 'guard-acquire')
fault = os.environ.get('FIXTURE_FAULT', '') if claim else ''
root = Path(os.environ['FIXTURE_ROOT'])
def hold():
    (root / 'held').touch()
    deadline = time.monotonic() + 15
    while not (root / 'continue').exists():
        if time.monotonic() > deadline:
            raise RuntimeError('Fixture release timeout')
        time.sleep(.01)
atomic = state.atomic_text
def write(path, value):
    atomic(path, value)
    target = ('vm-operation.lock', 'vm-name') if action == 'begin' else ('vm-state.guard', 'token')
    if fault == 'metadata-cancel' and path.parts[-2:] == target:
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
state.atomic_text = write
original_print = builtins.print
def output(*args, **kwargs):
    if fault == 'output-error' and kwargs.get('file') is not sys.stderr:
        raise BrokenPipeError('Synthetic token output failure')
    original_print(*args, **kwargs)
    if fault == 'output-cancel':
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
if claim:
    owners = [sys.argv[i + 1] for i, value in enumerate(sys.argv) if value == '--owner']
    (root / 'claim-owner.pid').write_text(owners[-1])
    builtins.print = output
try:
    if fault == 'hold-before-create':
        hold()
    status = state.main()
    if fault == 'hold-after-create':
        hold()
    if fault == 'exit-error' and status == 0:
        status = 17
finally:
    if claim:
        (root / 'creator-finished').touch()
raise SystemExit(status)
'''

SHELL = r'''
set -euo pipefail
source "$1/scripts/vm-utils.sh"
VM_NAME=fixture
# Observe signal delivery in the real shell trap without scheduler sleeps.
trap() {
    if [ "$#" -eq 2 ] && [ "$2" = TERM ] && [[ "$1" != -* ]]; then
        builtin trap 'printf observed > "$FIXTURE_ROOT/shell-cancelled"; '"$1" TERM
    else
        builtin trap "$@"
    fi
}
printf '%s\n' "$BASHPID" > "$FIXTURE_ROOT/shell.pid"
callback() { printf 'ran\n' > "$FIXTURE_ROOT/callback"; }
case "$2" in
    operation) begin_vm_operation; callback;;
    nested)
        begin_vm_operation
        previous="$VM_OPERATION_TOKEN"
        if begin_vm_operation; then exit 99; fi
        [ "$VM_OPERATION_TOKEN" = "$previous" ]
        [ "$(cat "$RUN_DIR/vm-operation.lock/token")" = "$previous" ]
        callback;;
    operation-keep)
        cleanup() { local status=$?; trap - EXIT; release_vm_operation || status=1; exit "$status"; }
        trap cleanup EXIT
        trap 'exit 130' INT
        trap 'exit 143' TERM
        begin_vm_operation keep-traps
        callback;;
    guard) with_vm_state_guard callback;;
esac
'''


class ShellHandoffTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.bash = os.environ.get('BASH_TEST_BINARY') or shutil.which('bash')
        self.assertTrue(self.bash, 'Real Bash is required')
        interpreter = self.root / 'interpreter.py'
        interpreter.write_text(INTERPRETER)
        self.interpreter = interpreter
        shim = self.root / 'python-fixture'
        shim.write_text('#!/usr/bin/env bash\nexec ' + shlex.quote(Path(sys.executable).as_posix()) +
                        ' ' + shlex.quote(interpreter.as_posix()) + ' "$@"\n')
        shim.chmod(0o755)
        self.environment = dict(os.environ, QEMU_ALPINE_BASE_DIR=str(self.root / 'state'),
            QEMU_STATE_PYTHON=shim.as_posix(), QEMU_ALPINE_SKIP_MSYS2_PATH='1',
            FIXTURE_ROOT=str(self.root), PYTHONDONTWRITEBYTECODE='1')
        self.environment.pop('VM_OPERATION_TOKEN', None)

    def start(self, kind, fault=''):
        return subprocess.Popen([self.bash, '-c', SHELL, 'fixture', ROOT.as_posix(), kind],
            env=dict(self.environment, FIXTURE_FAULT=fault), stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def assert_clean(self):
        self.assertFalse((self.root / 'state/run/vm-operation.lock').exists())
        self.assertFalse((self.root / 'state/run/vm-state.guard').exists())

    def test_success_installs_cleanup_and_runs_callback(self):
        for kind in ('operation', 'operation-keep', 'guard', 'nested'):
            with self.subTest(kind=kind):
                child = self.start(kind)
                _, errors = child.communicate(timeout=20)
                self.assertEqual(child.returncode, 0, errors.decode(errors='replace'))
                self.assertTrue((self.root / 'callback').exists())
                (self.root / 'callback').unlink()
                self.assert_clean()

    def test_cli_rolls_back_before_failed_token_delivery(self):
        for action in ('begin', 'guard-acquire'):
            for fault in ('metadata-cancel', 'output-error', 'output-cancel'):
                with self.subTest(action=action, fault=fault):
                    base = self.root / ('cli-' + action + '-' + fault)
                    run = base / 'run'
                    command = [sys.executable, str(self.interpreter), str(ROOT / 'scripts/vm-state.py'),
                        action, '--name', 'fixture', '--owner', str(os.getpid()), '--token', 'fixture-token',
                        '--vm-dir', str(base / 'vms'), '--run-dir', str(run),
                        '--active-lock', str(run / 'active-vm.lock'), '--state-guard', str(run / 'vm-state.guard')]
                    result = subprocess.run(command, env=dict(self.environment, FIXTURE_FAULT=fault),
                        capture_output=True, timeout=10)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse((run / 'vm-operation.lock').exists())
                    self.assertFalse((run / 'vm-state.guard').exists())

    def test_cli_cancellation_and_output_failures_are_clean_and_retryable(self):
        for kind in ('operation', 'operation-keep', 'guard'):
            for fault in ('metadata-cancel', 'output-error', 'output-cancel', 'exit-error'):
                with self.subTest(kind=kind, fault=fault):
                    child = self.start(kind, fault)
                    _, errors = child.communicate(timeout=20)
                    self.assertNotEqual(child.returncode, 0, errors.decode(errors='replace'))
                    self.assertFalse((self.root / 'callback').exists())
                    self.assert_clean()
                    retry = self.start(kind)
                    _, errors = retry.communicate(timeout=20)
                    self.assertEqual(retry.returncode, 0, errors.decode(errors='replace'))
                    (self.root / 'callback').unlink()
                    self.assert_clean()

    def wait_for(self, path, child):
        deadline = time.monotonic() + 10
        while not path.exists():
            self.assertIsNone(child.poll(), 'Shell exited before fixture barrier')
            self.assertLess(time.monotonic(), deadline, 'Fixture barrier timed out')
            time.sleep(.01)

    def test_shell_cancel_joins_creator_before_rollback(self):
        for kind in ('operation', 'operation-keep', 'guard'):
            for fault in ('hold-before-create', 'hold-after-create'):
                with self.subTest(kind=kind, fault=fault):
                    for name in ('held', 'continue', 'creator-finished', 'shell-cancelled'):
                        (self.root / name).unlink(missing_ok=True)
                    child = self.start(kind, fault)
                    try:
                        self.wait_for(self.root / 'held', child)
                        owner = (self.root / 'claim-owner.pid').read_text().strip()
                        subprocess.run([self.bash, '-c', 'kill -TERM "$1"', 'fixture', owner],
                            check=True, capture_output=True, timeout=5)
                        self.wait_for(self.root / 'shell-cancelled', child)
                        self.assertIsNone(child.poll())
                        self.assertFalse((self.root / 'creator-finished').exists())
                    finally:
                        # Always let the private creator exit, even on the broken
                        # baseline, so a failed regression leaves no live child.
                        (self.root / 'continue').touch()
                    _, errors = child.communicate(timeout=20)
                    deadline = time.monotonic() + 10
                    while not (self.root / 'creator-finished').exists():
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(.01)
                    self.assertNotEqual(child.returncode, 0, errors.decode(errors='replace'))
                    self.assertFalse((self.root / 'callback').exists())
                    self.assert_clean()

    def test_failed_claim_and_cleanup_preserve_existing_unknown_owner(self):
        for kind, directory in (('operation', 'vm-operation.lock'), ('guard', 'vm-state.guard')):
            with self.subTest(kind=kind):
                path = self.root / 'state/run' / directory
                path.mkdir(parents=True)
                marker = path / 'unknown'
                marker.write_text('retain preexisting ownership')
                child = self.start(kind)
                child.communicate(timeout=20)
                self.assertNotEqual(child.returncode, 0)
                self.assertEqual(marker.read_text(), 'retain preexisting ownership')
                self.assertFalse((self.root / 'callback').exists())
                marker.unlink()
                path.rmdir()
                self.assert_clean()


if __name__ == '__main__':
    unittest.main()
