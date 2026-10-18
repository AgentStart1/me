#!/usr/bin/env python3
"""Start exactly one profile-owned emulator under its per-AVD guard."""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys

from profile_controller import (FORBIDDEN_ARCH, apply_config, arguments, avd_config,
                                tool_environment, is_true, load_profile, native_path, read_config, resolve_tool, tool_command)


class Cancelled(Exception):
    def __init__(self, number):
        self.status = 128 + number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', nargs='?')
    args = parser.parse_args()
    default_dir = os.environ.get('ANDROID_PROFILE_DIR') or str(native_path(os.environ.get('HOME') or str(Path.home())) / 'android-profiles')
    profile = args.profile or os.environ.get('ANDROID_PROFILE') or str(Path(default_dir) / 'mobile.profile')
    guard = None
    owned_guard = False
    child = None
    status = 0
    def cancel(number, _frame):
        raise Cancelled(number)
    numbers = [signal.SIGTERM, signal.SIGINT] + ([signal.SIGBREAK] if hasattr(signal, 'SIGBREAK') else [])
    for number in numbers:
        signal.signal(number, cancel)
    try:
        loaded = load_profile(profile)
        if set(loaded).intersection(FORBIDDEN_ARCH):
            raise ValueError('profile must not define architecture; architecture is detected dynamically')
        values = loaded
        environment = tool_environment(values)
        if not values.get('AVD_NAME'):
            raise ValueError('required profile key AVD_NAME is missing or empty')
        executable = resolve_tool('emulator', environment)
        config = avd_config({**{key: environment[key] for key in ('HOME', 'ANDROID_AVD_HOME', 'ANDROID_USER_HOME') if key in environment}, **values})
        guard = config.with_name(config.name + '.profile-start.guard')
        try:
            guard.mkdir()
        except OSError as error:
            raise ValueError('AVD start guard is busy or its directory is unavailable; inspect the owning launch before recovery') from error
        owned_guard = True
        if any(config.parent.glob('*.lock')):
            raise ValueError('Existing AVD lock; confirm its emulator has stopped before manual recovery. Configuration was not changed.')
        wipe = False
        if config.is_file() and values.get('EMULATOR_CONFIG_disk__dataPartition__size'):
            current = read_config(config)
            if current.get('disk.dataPartition.size') != values['EMULATOR_CONFIG_disk__dataPartition__size']:
                userdata = any((config.parent / name).exists() for name in ('userdata-qemu.img', 'userdata-qemu.img.qcow2'))
                custom = values.get('EMULATOR_VALUE_data') or current.get('disk.dataPartition.path')
                if userdata or custom:
                    if not is_true(values.get('EMULATOR_ALLOW_DATA_WIPE')):
                        raise ValueError('Resizing existing AVD data requires explicit EMULATOR_ALLOW_DATA_WIPE=true')
                    wipe = True
        apply_config(config, values)
        command = ['-avd', values['AVD_NAME']] + (['-wipe-data'] if wipe else []) + arguments(values, 'EMULATOR', '-')
        print('Starting emulator...', flush=True)
        child = subprocess.Popen(tool_command(executable, command), env=environment, start_new_session=os.name != 'nt',
                                 creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
        while True:
            try:
                status = child.wait(timeout=.2)
                break
            except subprocess.TimeoutExpired:
                continue
        if status < 0:
            status = 128 - status
        print('Emulator process has exited.', flush=True)
    except Cancelled as error:
        status = error.status
    except (OSError, ValueError) as error:
        print(f'Error: {error}', file=sys.stderr)
        status = 1
    finally:
        for number in numbers:
            signal.signal(number, signal.SIG_IGN)
        if child is not None and child.poll() is None:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if child.poll() is None:
                    child.terminate()
            else:
                os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name == 'nt':
                    child.kill()
                else:
                    os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        if owned_guard:
            try:
                guard.rmdir()
            except OSError:
                print('Error: Failed to remove owned AVD start guard', file=sys.stderr)
                status = status or 1
    return status


if __name__ == '__main__':
    sys.exit(main())
