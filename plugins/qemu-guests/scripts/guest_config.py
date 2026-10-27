"""Validated work-guest profiles; Alpine backend profiles remain independent."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def integer(value, label, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label} must be an integer in {low}..{high}')
    return value


def load(path):
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding='utf-8'))
    allowed = {'name', 'os', 'state_dir', 'qemu', 'qemu_img', 'memory', 'cpus',
               'disk_size', 'base_image', 'installer_iso', 'media_sha256', 'ssh_port',
               'ssh_user', 'access_key', 'appium', 'qemu_args',
               'install_args', 'hardware_args', 'timeout', 'windows_image', 'seed_dir', 'acceptance',
               'graphical', 'qmp_port', 'macos', 'install_reboots', 'qemu_runtime'}
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValueError('Unknown guest profile keys')
    for key in ('name', 'os', 'state_dir', 'ssh_port', 'access_key', 'appium'):
        if key not in data:
            raise ValueError(f'Missing guest profile key: {key}')
    if not isinstance(data['name'], str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', data['name']):
        raise ValueError('name must be a simple identifier')
    if data['os'] not in {'ubuntu', 'windows', 'macos', 'custom'}:
        raise ValueError('os must be ubuntu, windows, macos or custom')
    data['qemu_runtime'] = data.get('qemu_runtime',
        'whpx-reset' if os.name == 'nt' and data['os'] == 'windows' and not data.get('qemu') else 'system')
    if data['qemu_runtime'] not in {'system', 'whpx-reset', 'reims-whpx', 'virgl-whpx'}:
        raise ValueError('qemu_runtime must be system, whpx-reset, reims-whpx or virgl-whpx')
    if data['qemu_runtime'] == 'reims-whpx' and data['os'] != 'macos':
        raise ValueError('reims-whpx is reserved for Intel macOS guests')
    if 'base_image' in data and 'installer_iso' in data:
        raise ValueError('Choose base_image or installer_iso, not both')
    for key in ('state_dir', 'base_image', 'installer_iso', 'access_key', 'seed_dir'):
        if key in data:
            value = Path(data[key]).expanduser()
            data[key] = str((path.parent / value).resolve() if not value.is_absolute() else value.resolve())
    appium = data['appium']
    if not isinstance(appium, dict) or set(appium) != {'host_port', 'runtime_archive', 'sha256'}:
        raise ValueError('appium requires host_port, runtime_archive and sha256')
    integer(appium['host_port'], 'appium.host_port', 1024, 65535)
    archive = Path(appium['runtime_archive']).expanduser()
    appium['runtime_archive'] = str((path.parent / archive).resolve() if not archive.is_absolute() else archive.resolve())
    integer(data['ssh_port'], 'ssh_port', 1, 65535)
    data['graphical'] = data.get('graphical', data['os'] in {'windows', 'macos'})
    if type(data['graphical']) is not bool:
        raise ValueError('graphical must be true or false')
    if data['qemu_runtime'] == 'virgl-whpx' and (data['os'] != 'ubuntu' or not data['graphical']):
        raise ValueError('virgl-whpx requires a graphical Ubuntu guest')
    if data['graphical'] or data['os'] == 'macos':
        integer(data.get('qmp_port'), 'qmp_port (required for graphical guests)', 1024, 65535)
        if data['qmp_port'] in (data['ssh_port'], appium['host_port']):
            raise ValueError('QMP/SSH ports collide')
    if data['ssh_port'] == appium['host_port']:
        raise ValueError('SSH/Appium ports collide')
    for name, default, low, high in [('memory', 4096, 512, 1048576), ('cpus', 4, 1, 1024), ('timeout', 3600, 1, 86400)]:
        data[name] = integer(data.get(name, default), name, low, high)
    data['disk_size'] = data.get('disk_size', '64G')
    data['install_reboots'] = integer(data.get('install_reboots', 0), 'install_reboots', 0, 10)
    if data['install_reboots'] and data['os'] != 'windows':
        raise ValueError('install_reboots is supported only for Windows installation')
    if not re.fullmatch(r'[1-9][0-9]*[GM]', data['disk_size']):
        raise ValueError('disk_size must be a positive G/M size')
    data['ssh_user'] = data.get('ssh_user', 'developer')
    if not re.fullmatch('[a-z][a-z0-9_-]*', data['ssh_user']):
        raise ValueError('ssh_user must be a simple account name')
    for name in ('qemu_args', 'install_args', 'acceptance', 'hardware_args'):
        default = ['-accel', 'whpx', '-cpu', 'Westmere,-vmx,-svm'] if name == 'qemu_args' and data['qemu_runtime'] in {'whpx-reset', 'virgl-whpx'} else []
        if name == 'qemu_args' and data['qemu_runtime'] == 'reims-whpx':
            from reims_runtime import CPU_ARGS
            default = CPU_ARGS
        values = data.get(name, default)
        if not isinstance(values, list) or any(not isinstance(v, str) or '\x00' in v for v in values):
            raise ValueError(f'{name} must be an argument array')
        data[name] = values
    if data['qemu_runtime'] == 'whpx-reset' and data['install_reboots']:
        raise ValueError('Managed WHPX reset uses warm reboots; set install_reboots to 0')
    if data['os'] == 'ubuntu' and 'base_image' not in data:
        raise ValueError('Ubuntu requires a cloud-init enabled qcow2 base_image')
    if data['os'] == 'windows' and 'installer_iso' not in data:
        raise ValueError('Windows requires installer_iso')
    if data['os'] == 'macos':
        settings = data.get('macos', {})
        if not isinstance(settings, dict) or set(settings) != {'installer_app', 'target_disk', 'bootstrap_package', 'tesseract'}:
            raise ValueError('macos requires installer_app, target_disk, bootstrap_package and tesseract')
        if not isinstance(settings['target_disk'], str) or not re.fullmatch(
                r'/dev/disk[0-9]+|serial:[a-zA-Z0-9_-]{1,64}', settings['target_disk']):
            raise ValueError('macos.target_disk must identify an explicit BSD disk or serial')
        if not isinstance(settings['installer_app'], str) or not settings['installer_app'].startswith('/Volumes/') or '\n' in settings['installer_app']:
            raise ValueError('macos.installer_app must be a guest /Volumes path')
        package = Path(settings['bootstrap_package']).expanduser()
        settings['bootstrap_package'] = str((path.parent / package).resolve() if not package.is_absolute() else package.resolve())
        if not data.get('installer_iso') or not data['hardware_args']:
            raise ValueError('macos requires prepared bootable installer media and compatible hardware_args')
    if data['os'] == 'custom' and (not data.get('seed_dir') or not data['acceptance'] or not data['install_args']):
        raise ValueError('custom requires seed_dir, install_args and acceptance; no universal installer is bundled')
    return data


def verify_inputs(config):
    if config.get('qemu_runtime') == 'virgl-whpx' and 'runtime_requirements' not in config:
        raise ValueError('Install virgl-whpx with --requirements for the desktop runtime')
    if config['os'] == 'macos':
        if not Path(config['macos']['bootstrap_package']).is_file():
            raise ValueError('Build the macOS bootstrap product package before installation')
        subprocess.run([config['macos']['tesseract'], '--version'], check=True, capture_output=True, timeout=10)
    for key in ('access_key',):
        if not Path(config[key]).is_file():
            raise ValueError(f'Missing {key}')
    if not Path(config['access_key'] + '.pub').is_file():
        raise ValueError('Missing access public key')
    check_digest(config['appium']['runtime_archive'], config['appium']['sha256'], 'Appium runtime')
    from test_requirements import verify_runtime, verify_runtime_target
    if 'runtime_requirements' in config:
        from initialization_snapshot import record_for
        verify_runtime(config['appium']['runtime_archive'], record_for(config), config['os'])
    else:
        verify_runtime_target(config['appium']['runtime_archive'], config['os'])
    media = config.get('base_image') or config.get('installer_iso')
    expected = config.get('media_sha256', '')
    if not media or not re.fullmatch('[a-fA-F0-9]{64}', expected):
        raise ValueError('A local base_image/installer_iso and media_sha256 are required')
    check_digest(media, expected, 'Installation media')


def check_digest(path, expected, label):
    if not isinstance(expected, str) or not re.fullmatch('[a-fA-F0-9]{64}', expected):
        raise ValueError(f'{label} requires sha256')
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    if digest.hexdigest() != expected.lower():
        raise ValueError(f'{label} checksum mismatch')
