"""Render private unattended installation media and guest-local Docker forwarding."""
import base64
import io
import json
from pathlib import Path
import secrets
import re
import shlex
import zipfile
from xml.sax.saxutils import escape

TEMPLATES = Path(__file__).resolve().parents[1] / 'templates' / 'guests'


def render(name, values):
    content = (TEMPLATES / name).read_text(encoding='utf-8')
    for key, value in values.items():
        content = content.replace('{{' + key + '}}', str(value))
    if '{{' in content:
        raise ValueError(f'Unresolved template value in {name}')
    return content


def tunnel_arguments(config, key):
    backend = config['backend']
    forwards = ['-L', '127.0.0.1:2375:127.0.0.1:2375']
    for port in range(backend['publish_start'], backend['publish_end'] + 1):
        forwards += ['-L', f'127.0.0.1:{port}:127.0.0.1:{port}']
    return ['-N', '-o', 'BatchMode=yes', '-o', 'ExitOnForwardFailure=yes',
            '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
            '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null',
            '-i', key, '-p', str(backend['ssh_port']), *forwards, 'root@10.0.2.2']


def payload(config):
    windows = config['os'] == 'windows'
    home = 'C:/ProgramData/qemu-guests' if windows else '/opt/qemu-guests'
    args = tunnel_arguments(config, home + ('/backend-tunnel-key' if windows else '/backend-key'))
    # Templates are program text; values here are validated identifiers/integers
    # or JSON/base64 strings rather than shell-interpolated user configuration.
    files = {
        'backend-key': Path(config['backend']['key']).read_bytes(),
        'docker.exe' if windows else 'docker': Path(config['proxy_binary']).read_bytes(),
    }
    public = Path(config['access_key'] + '.pub').read_text().split()
    if len(public) < 2 or public[0] != 'ssh-ed25519' or not re.fullmatch('[A-Za-z0-9+/=]+', public[1]):
        raise ValueError('access_key must have an Ed25519 public key')
    public_key = ' '.join(public[:2])
    values = {'SSH_PORT': config['backend']['ssh_port'], 'USER': config['ssh_user'],
              'PUBLIC_KEY': public_key,
              'TUNNEL_ARGS': ' '.join(args),
              'PS_TUNNEL_ARGS': ','.join("'" + a.replace("'", "''") + "'" for a in args),
              'POOL_START': config['backend']['publish_start'], 'POOL_END': config['backend']['publish_end']}
    if windows:
        files['backend-tunnel-key'] = files['backend-key']
        files['bootstrap.ps1'] = render('bootstrap.ps1.tpl', values).encode()
        files['verify.ps1'] = render('verify.ps1.tpl', values).encode()
    else:
        files['environment'] = render('environment.sh.tpl', values).encode()
        files['environment.pam'] = render('environment.pam.tpl', values).encode()
        files['docker-tunnel.service'] = render('docker-tunnel.service.tpl', values).encode()
        files['docker-tunnel.plist'] = render('docker-tunnel.plist.tpl', {
            'ARGUMENTS': ''.join('<string>' + escape(v) + '</string>' for v in ['/usr/bin/ssh', *args])}).encode()
        files['bootstrap.sh'] = render('bootstrap.sh.tpl', values).encode()
        files['verify.py'] = render('verify.py.tpl', values).encode()
        if config['os'] == 'macos':
            files['macos-firstboot.sh'] = render('macos-firstboot.sh.tpl', values).encode()
            files['macos-firstboot.plist'] = render('macos-firstboot.plist.tpl', {}).encode()
            files['account-password'] = secrets.token_urlsafe(24).encode()
            files['access.pub'] = public_key.encode()
            files['verify-macos.sh'] = render('verify-macos.sh.tpl', values).encode()
    return files


def payload_archive(config):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in payload(config).items():
            archive.writestr(name, content)
    return buffer.getvalue()


def prepare_seed(config, directory):
    directory = Path(directory)
    directory.mkdir(mode=0o700)
    files = payload(config) if config['os'] != 'macos' else {}
    if config['os'] != 'macos':
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        (directory / 'payload.zip').write_bytes(buffer.getvalue())
    if config['os'] == 'ubuntu':
        entries = [{'path': '/opt/qemu-guests/' + name, 'encoding': 'b64',
                    'content': base64.b64encode(content).decode(), 'permissions': '0600'}
                   for name, content in files.items()]
        user = {'name': config['ssh_user'], 'shell': '/bin/bash', 'sudo': 'ALL=(ALL) NOPASSWD:ALL',
                'ssh_authorized_keys': [Path(config['access_key'] + '.pub').read_text().strip()]}
        cloud = {'users': [user], 'ssh_pwauth': False, 'packages': ['openssh-client', 'openssh-server'],
                 'write_files': entries, 'runcmd': [['bash', '/opt/qemu-guests/bootstrap.sh']]}
        if config.get('graphical'):
            cloud['packages'] += ['xfce4', 'lightdm', 'lightdm-gtk-greeter', 'xserver-xorg']
            cloud['runcmd'].extend([['systemctl', 'set-default', 'graphical.target'], ['systemctl', 'start', 'lightdm']])
        (directory / 'user-data').write_text('#cloud-config\n' + json.dumps(cloud), encoding='utf-8')
        (directory / 'meta-data').write_text(json.dumps({'instance-id': config['name'], 'local-hostname': config['name']}), encoding='utf-8')
    elif config['os'] == 'windows':
        image = config.get('windows_image', 'Windows 10 Pro')
        (directory / 'Autounattend.xml').write_text(render('Autounattend.xml.tpl', {
            'USER': config['ssh_user'], 'PASSWORD': 'Qemu!' + secrets.token_urlsafe(24),
            'IMAGE': escape(image),
        }), encoding='utf-8')
    elif config['os'] == 'macos':
        settings = config['macos']
        (directory / 'bootstrap.pkg').write_bytes(Path(settings['bootstrap_package']).read_bytes())
        (directory / 'macos-install.sh').write_text(render('macos-install.sh.tpl', {
            'TARGET_DISK': shlex.quote(settings['target_disk']),
            'INSTALLER_APP': shlex.quote(settings['installer_app']),
        }), encoding='utf-8')
    else:
        for source in Path(config['seed_dir']).iterdir():
            target = directory / source.name
            if target.exists():
                raise ValueError('Custom seed cannot replace generated payload.zip')
            if not source.is_file() or source.is_symlink():
                raise ValueError('Custom seed must contain flat regular files')
            target.write_bytes(source.read_bytes())
    # pycdlib provides cross-platform media creation without mounting or admin access.
    import pycdlib
    iso = pycdlib.PyCdlib()
    iso.new(interchange_level=3, joliet=3, vol_ident='cidata' if config['os'] == 'ubuntu' else 'GUESTSEED')
    index = 0
    for source in sorted(directory.rglob('*')):
        relative = source.relative_to(directory).as_posix()
        # Installer adapters use Joliet paths. The ISO9660 tree has stable aliases.
        if source.is_dir():
            raise ValueError('Custom seed files must be flat; use an archive for nested payloads')
        index += 1
        iso.add_file(str(source), iso_path=f'/F{index:07d}.DAT;1', joliet_path='/' + relative)
    try:
        iso.write(str(directory.parent / 'seed.iso'))
    finally:
        iso.close()
