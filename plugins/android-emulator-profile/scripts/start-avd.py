#!/usr/bin/env python3
"""Start exactly one profile-owned emulator under its per-AVD guard."""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys

from command_tree import CommandTree, creation_handoff

from profile_controller import (FORBIDDEN_ARCH, apply_config, arguments, avd_config,
                                tool_environment, is_true, load_profile, native_path, read_config, resolve_tool, tool_command)


class Cancelled(Exception):
    def __init__(self, number):
        self.status = 128 + number


class AvdSession:
    """Keep the configuration guard until every owned command has stopped."""
    def __init__(self, config):
        self.config = config
        self.guard = config.with_name(config.name + '.profile-start.guard')
        self.tree = CommandTree()

    def __enter__(self):
        acquired = False
        try:
            with creation_handoff():
                try:
                    self.guard.mkdir()
                except OSError as error:
                    raise ValueError('AVD start guard is busy or its directory is unavailable; inspect the owning launch before recovery') from error
                acquired = True
            return self
        except BaseException:
            if acquired:
                self.guard.rmdir()
            raise

    def start(self, command, environment):
        return self.tree.start(command, env=environment)

    def __exit__(self, _kind, original, _traceback):
        previous = {number: signal.signal(number, signal.SIG_IGN) for number in cancellation_signals()}
        try:
            # Failed tree cleanup deliberately preserves the guard for recovery.
            self.tree.stop()
            self.guard.rmdir()
        except (OSError, subprocess.SubprocessError) as error:
            print(f'AVD cleanup failed; guard retained for recovery: {error}', file=sys.stderr)
            if original is None:
                raise
            # Preserve an original cancellation/failure without discarding evidence.
            return False
        finally:
            for number, handler in previous.items():
                signal.signal(number, handler)


def cancellation_signals():
    return [signal.SIGTERM, signal.SIGINT] + ([signal.SIGBREAK] if hasattr(signal, 'SIGBREAK') else [])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', nargs='?')
    args = parser.parse_args()
    default_dir = os.environ.get('ANDROID_PROFILE_DIR') or str(native_path(os.environ.get('HOME') or str(Path.home())) / 'android-profiles')
    profile = args.profile or os.environ.get('ANDROID_PROFILE') or str(Path(default_dir) / 'mobile.profile')
    status = 0
    def cancel(number, _frame):
        raise Cancelled(number)
    numbers = cancellation_signals()
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
        with AvdSession(config) as session:
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
            child = session.start(tool_command(executable, command), environment)
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
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'Error: {error}', file=sys.stderr)
        status = status or 1
    return status


if __name__ == '__main__':
    sys.exit(main())
