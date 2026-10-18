#!/usr/bin/env python3
"""Literal Android profiles, tool boundaries, arguments and atomic AVD configuration."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from command_tree import script_command

FORBIDDEN_ARCH = ('ARCH', 'ABI', 'AVD_ARCH', 'AVD_ABI', 'AVDMANAGER_ABI', 'AVDMANAGER_ARCH', 'EMULATOR_ABI', 'EMULATOR_ARCH')


# Only these profile paths are also part of the Android tools' environment contract.
ANDROID_PATHS = ('ANDROID_HOME', 'ANDROID_AVD_HOME', 'ANDROID_USER_HOME')


def tool_environment(profile, inherited=None):
    environment = dict(os.environ if inherited is None else inherited)
    for key in ANDROID_PATHS:
        if key in profile:
            environment[key] = profile[key]
        if os.name == 'nt' and environment.get(key):
            environment[key] = str(native_path(environment[key]))
    if profile.get('EMULATOR_DISPLAY'):
        environment['DISPLAY'] = profile['EMULATOR_DISPLAY']
    return environment


def native_path(value):
    if os.name == 'nt' and value.startswith('/') and shutil.which('cygpath'):
        return Path(subprocess.check_output(['cygpath', '-w', value], encoding='utf-8').strip())
    return Path(value)


def load_profile(path):
    values = {}
    for number, line in enumerate(native_path(str(path)).read_text(encoding='utf-8').splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        match = re.fullmatch(r'([A-Za-z_][A-Za-z0-9_]*)=(.*)', line)
        if not match:
            raise ValueError(f'invalid profile line {number}')
        key, value = match.groups()
        if '$' in value or '`' in value or '\x00' in value:
            raise ValueError(f'shell expansion is not allowed at profile line {number}')
        value = value.strip()
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f'unmatched profile quotes at line {number}')
            value = value[1:-1]
        values[key] = value
    return values


def is_true(value):
    return value in ('true', 'TRUE', 'yes', 'YES', '1', 'on', 'ON')


def arguments(values, prefix, dash, excludes=()):
    result = []
    for kind in ('FLAG', 'VALUE'):
        marker = prefix + '_' + kind + '_'
        for key in sorted(values):
            if not key.startswith(marker):
                continue
            name = key[len(marker):]
            value = values[key]
            if name in excludes:
                continue
            if kind == 'FLAG' and is_true(value):
                result.append(dash + name.replace('_', '-'))
            elif kind == 'VALUE' and value:
                result.extend((dash + name.replace('_', '-'), value))
    return result


def resolve_tool(name, values):
    sdk = native_path(values.get('ANDROID_HOME') or str(native_path(values.get('HOME') or str(Path.home())) / 'android-sdk'))
    suffixes = ('', '.bat', '.cmd', '.exe')
    # Preserve PATH before SDK fallback and extension ordering within each directory.
    for directory in os.get_exec_path(values):
        for suffix in suffixes:
            candidate = Path(directory) / (name + suffix)
            if candidate.is_file() and (os.name == 'nt' or os.access(candidate, os.X_OK)):
                return candidate
    directory = {'sdkmanager': sdk / 'cmdline-tools/latest/bin', 'avdmanager': sdk / 'cmdline-tools/latest/bin',
                 'adb': sdk / 'platform-tools', 'emulator': sdk / 'emulator'}.get(name)
    if directory:
        for suffix in suffixes:
            candidate = directory / (name + suffix)
            if candidate.is_file():
                return candidate
    raise ValueError(f'Android tool not found: {name}. Add it to PATH or set ANDROID_HOME.')


def tool_command(executable, args):
    path = Path(executable)
    if os.name == 'nt' and path.suffix.lower() in ('.bat', '.cmd'):
        # cmd reparses its command string; reject values whose quoting cannot
        # be represented safely rather than silently executing profile data.
        tokens = [str(path), *args]
        if any(any(char in value for char in '\r\n"%!^&|<>') or value.endswith('\\') for value in tokens):
            raise ValueError('Unsupported metacharacter or trailing backslash in Windows batch tool argument')
        return subprocess.list2cmdline([os.environ.get('COMSPEC', 'cmd.exe')]) + ' /d /s /c "' + ' '.join('"' + value + '"' for value in tokens) + '"'
    return script_command(path, *args)


def avd_config(values):
    home = values.get('HOME') or str(Path.home())
    avd_home = native_path(values.get('ANDROID_AVD_HOME') or str(native_path(values.get('ANDROID_USER_HOME') or str(native_path(home) / '.android')) / 'avd'))
    directory = values.get('AVDMANAGER_VALUE_path')
    if not directory:
        ini = avd_home / (values['AVD_NAME'] + '.ini')
        if ini.is_file():
            directory = read_config(ini).get('path')
    return (native_path(directory) if directory else avd_home / (values['AVD_NAME'] + '.avd')) / 'config.ini'


def read_config(path):
    values = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        key, separator, value = line.partition('=')
        if separator and key not in values:
            values[key] = value
    return values


def apply_config(path, values):
    overrides = {key[len('EMULATOR_CONFIG_'):].replace('__', '.'): values[key]
                 for key in sorted(values) if key.startswith('EMULATOR_CONFIG_')}
    if not overrides:
        return
    original = path.read_text(encoding='utf-8').splitlines()
    lines = []
    pending = dict(overrides)
    for line in original:
        key, separator, _ = line.partition('=')
        if separator and key in overrides:
            if key in pending:
                lines.append(key + '=' + pending.pop(key))
        else:
            lines.append(line)
    lines.extend(key + '=' + value for key, value in pending.items())
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + '.tmp.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as output:
            output.write('\n'.join(lines) + '\n')
        shutil.copymode(path, temporary)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('profile', 'tool', 'args'))
    parser.add_argument('items', nargs='*')
    args = parser.parse_args()
    try:
        if args.mode == 'profile':
            for key, value in load_profile(args.items[0]).items():
                sys.stdout.buffer.write(key.encode() + b'\0' + value.encode('utf-8') + b'\0')
        elif args.mode == 'tool':
            print(resolve_tool(args.items[0], {**os.environ, **({'ANDROID_HOME': args.items[1]} if len(args.items) > 1 and args.items[1] else {})}))
        else:
            prefix, dash, *remaining = args.items
            marker = remaining.index('@@')
            excludes = remaining[:marker]
            values = dict(item.split('=', 1) for item in remaining[marker + 1:])
            for value in arguments(values, prefix, dash, excludes):
                sys.stdout.buffer.write(value.encode('utf-8') + b'\0')
        return 0
    except (OSError, ValueError, IndexError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
