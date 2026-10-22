#!/usr/bin/env python3
"""Opt-in: reboot an already-ready four-vCPU Windows WHPX guest three times."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from guest_config import load
from guest_registry import entries, state
from guest_screen import Qmp
from process_identity import identity, owns_listeners


def wait_appium(ssh, unchanged, deadline):
    """SSH readiness precedes interactive Appium startup; share the cycle deadline."""
    command = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:/ProgramData/qemu-guests/verify.ps1'
    while True:
        unchanged()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError('Post-restart guest Appium acceptance timed out')
        try:
            result = ssh(command, min(15, remaining))
        except subprocess.TimeoutExpired:
            result = None
        unchanged()
        if result is not None and result.returncode == 0:
            return
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(3, remaining))


def validate(config, report, save, cycles, timeout):
    item = next(entry for entry in entries() if entry['state_dir'] == config['state_dir'])
    phase, record = state(item)
    if phase != 'ready' or not owns_listeners(record['pid'], {config['qmp_port']}):
        raise RuntimeError('Guest must be supervised and ready with its own QMP listener')

    def unchanged():
        if identity(record['pid']) != record['identity']:
            raise RuntimeError('QEMU exited or was replaced; cold restart does not pass')

    def qmp(command):
        unchanged()
        client = Qmp(config['qmp_port'])
        try:
            return client.execute(command)
        finally:
            client.close()

    def ssh(command, budget=15):
        unchanged()
        return subprocess.run([
            'ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=' + os.devnull, '-o', 'ConnectTimeout=2',
            '-i', config['access_key'], '-p', str(config['ssh_port']),
            config['ssh_user'] + '@127.0.0.1', command],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=budget)

    def processors():
        result = ssh('powershell.exe -NoProfile -Command "(Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors"')
        if result.returncode or result.stdout.strip() != '4':
            raise RuntimeError('Windows does not report four logical processors')

    boot_command = ('powershell.exe -NoProfile -Command "'
                    '(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString(\'o\')"')
    processors()
    initial = ssh(boot_command)
    if initial.returncode or not initial.stdout.strip():
        raise RuntimeError('Cannot read initial Windows boot time')
    before = initial.stdout.strip()
    report.update(pid=record['pid'], version=qmp('query-version'), initialBootTime=before)
    for cycle in range(1, cycles + 1):
        started = time.monotonic()
        result = ssh('shutdown /r /t 2')
        if result.returncode:
            raise RuntimeError('Windows rejected the restart request')
        time.sleep(6)
        while True:
            machine = qmp('query-status')
            if not machine['running']:
                report['failureState'] = machine
                raise RuntimeError('QEMU paused during Windows restart')
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise RuntimeError('Windows did not return before the restart deadline')
            try:
                result = ssh(boot_command, min(15, remaining))
            except subprocess.TimeoutExpired:
                result = None
            if result and not result.returncode and result.stdout.strip() not in {'', before}:
                before = result.stdout.strip()
                break
            time.sleep(min(3, max(0, timeout - (time.monotonic() - started))))
        processors()
        wait_appium(ssh, unchanged, started + timeout)
        unchanged()
        report['cycles'].append({'cycle': cycle, 'bootTime': before,
                                 'seconds': round(time.monotonic() - started, 2),
                                 'sameQemuProcess': True, 'processors': 4, 'appiumReady': True})
        save()
        print(f'Restart {cycle}/{cycles} passed in the same four-vCPU QEMU process.', flush=True)
    report['appiumReady'] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--cycles', type=int, default=3, choices=range(1, 11))
    parser.add_argument('--timeout', type=int, default=180)
    args = parser.parse_args()
    config = load(args.profile)
    values = config['qemu_args']
    accelerators = [values[i + 1] for i, value in enumerate(values[:-1]) if value == '-accel']
    if (os.name != 'nt' or config['os'] != 'windows' or config['cpus'] != 4
            or not config.get('qmp_port') or len(accelerators) != 1
            or accelerators[0].split(',')[0] != 'whpx' or args.timeout < 30):
        parser.error('Requires Windows host/guest, four vCPUs, QMP, explicit WHPX and timeout >= 30')
    report = {'accelerator': 'whpx', 'cycles': [], 'passed': False}

    def save():
        args.report.write_text(json.dumps(report, indent=2), encoding='utf-8')

    try:
        validate(config, report, save, args.cycles, args.timeout)
        report['passed'] = True
    except (OSError, ValueError, RuntimeError, StopIteration, subprocess.SubprocessError) as error:
        report['error'] = str(error) or type(error).__name__
        print('Restart validation failed: ' + report['error'], file=sys.stderr)
    finally:
        save()
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
