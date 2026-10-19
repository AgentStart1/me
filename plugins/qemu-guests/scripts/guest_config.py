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
               'ssh_user', 'access_key', 'backend', 'proxy_binary', 'qemu_args',
               'install_args', 'hardware_args', 'timeout', 'windows_image', 'seed_dir', 'acceptance',
               'graphical', 'qmp_port', 'macos', 'install_reboots', 'qemu_runtime'}
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValueError('Unknown guest profile keys')
    for key in ('name', 'os', 'state_dir', 'ssh_port', 'access_key', 'backend', 'proxy_binary'):
        if key not in data:
            raise ValueError(f'Missing guest profile key: {key}')
    if not isinstance(data['name'], str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', data['name']):
        raise ValueError('name must be a simple identifier')
    if data['os'] not in {'ubuntu', 'windows', 'macos', 'custom'}:
        raise ValueError('os must be ubuntu, windows, macos or custom')
    data['qemu_runtime'] = data.get('qemu_runtime',
        'whpx-reset' if os.name == 'nt' and data['os'] == 'windows' and not data.get('qemu') else 'system')
    if data['qemu_runtime'] not in {'system', 'whpx-reset'}:
        raise ValueError('qemu_runtime must be system or whpx-reset')
    if 'base_image' in data and 'installer_iso' in data:
        raise ValueError('Choose base_image or installer_iso, not both')
    for key in ('state_dir', 'base_image', 'installer_iso', 'access_key', 'proxy_binary', 'seed_dir'):
        if key in data:
            value = Path(data[key]).expanduser()
            data[key] = str((path.parent / value).resolve() if not value.is_absolute() else value.resolve())
    backend = data['backend']
    if not isinstance(backend, dict) or set(backend) != {'ssh_port', 'key', 'publish_start', 'publish_end'}:
        raise ValueError('backend requires ssh_port, key, publish_start and publish_end')
    key = Path(backend['key']).expanduser()
    backend['key'] = str((path.parent / key).resolve() if not key.is_absolute() else key.resolve())
    integer(data['ssh_port'], 'ssh_port', 1, 65535)
    data['graphical'] = data.get('graphical', data['os'] in {'windows', 'macos'})
    if type(data['graphical']) is not bool:
        raise ValueError('graphical must be true or false')
    if data['graphical'] or data['os'] == 'macos':
        integer(data.get('qmp_port'), 'qmp_port (required for graphical guests)', 1024, 65535)
        if data['qmp_port'] in (data['ssh_port'], backend['ssh_port']):
            raise ValueError('QMP/SSH ports collide')
    integer(backend['ssh_port'], 'backend.ssh_port', 1, 65535)
    start = integer(backend['publish_start'], 'backend.publish_start', 1024, 65535)
    end = integer(backend['publish_end'], 'backend.publish_end', start, 65535)
    if start <= 2375 <= end or start <= backend['ssh_port'] <= end or data['ssh_port'] == backend['ssh_port']:
        raise ValueError('SSH/API/publish ports collide')
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
        default = ['-accel', 'whpx', '-cpu', 'Westmere,-vmx,-svm'] if name == 'qemu_args' and data['qemu_runtime'] == 'whpx-reset' else []
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
        if not re.fullmatch(r'/dev/disk[0-9]+', settings['target_disk']):
            raise ValueError('macos.target_disk must identify one explicit guest disk')
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
    if config['os'] == 'macos':
        if not Path(config['macos']['bootstrap_package']).is_file():
            raise ValueError('Build the macOS bootstrap product package before installation')
        subprocess.run([config['macos']['tesseract'], '--version'], check=True, capture_output=True, timeout=10)
    for key in ('access_key', 'proxy_binary'):
        if not Path(config[key]).is_file():
            raise ValueError(f'Missing {key}')
    if not Path(config['access_key'] + '.pub').is_file() or not Path(config['backend']['key']).is_file():
        raise ValueError('Missing access public key or backend private key')
    media = config.get('base_image') or config.get('installer_iso')
    expected = config.get('media_sha256', '')
    if not media or not re.fullmatch('[a-fA-F0-9]{64}', expected):
        raise ValueError('A local base_image/installer_iso and media_sha256 are required')
    digest = hashlib.sha256()
    with open(media, 'rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    if digest.hexdigest() != expected.lower():
        raise ValueError('Installation media checksum mismatch')
