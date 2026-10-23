"""Render private unattended installation media for Appium test guests."""
import base64
import io
import json
from pathlib import Path
import secrets
import re
import shlex
import zipfile
from xml.sax.saxutils import escape
from initialization_snapshot import record_for

TEMPLATES = Path(__file__).resolve().parents[1] / 'templates' / 'guests'


def render(name, values):
    content = (TEMPLATES / name).read_text(encoding='utf-8')
    for key, value in values.items():
        content = content.replace('{{' + key + '}}', str(value))
    if '{{' in content:
        raise ValueError(f'Unresolved template value in {name}')
    return content


def payload(config):
    windows = config['os'] == 'windows'
    # Templates are program text; values here are validated identifiers/integers
    # or JSON/base64 strings rather than shell-interpolated user configuration.
    files = {'appium-runtime.zip': Path(config['appium']['runtime_archive']).read_bytes(),
             'appium-run.cjs': render('appium-run.cjs.tpl', {}).encode(),
             'relocate-runtime.cjs': render('relocate-runtime.cjs.tpl', {}).encode()}
    public = Path(config['access_key'] + '.pub').read_text().split()
    if len(public) < 2 or public[0] != 'ssh-ed25519' or not re.fullmatch('[A-Za-z0-9+/=]+', public[1]):
        raise ValueError('access_key must have an Ed25519 public key')
    public_key = ' '.join(public[:2])
    values = {'USER': config['ssh_user'], 'PUBLIC_KEY': public_key}
    requirements = record_for(config)
    desktop = requirements['desktop'] if requirements is not None else config.get('desktop')
    if desktop is not None:
        files['desktop.json'] = json.dumps(desktop).encode()
        if requirements is not None:
            files['runtime-requirements.json'] = json.dumps(requirements['runtime']).encode()
            snapshot = config.get('initialization_snapshot')
            if snapshot is None and requirements['hooks']['guest_setup']:
                raise ValueError('Guest scripts require an initialization snapshot; supply project requirements')
            if snapshot is not None:
                files.update(snapshot.guest_files)
            files['setup-hooks.json'] = snapshot.guest_hooks_json if snapshot is not None else b'[]'
            files['run-setup-hooks.cjs'] = render('run-setup-hooks.cjs.tpl', {}).encode()
        files['desktop-session.sh'] = render('desktop-session.sh.tpl', {
            'WIDTH': desktop['width'], 'HEIGHT': desktop['height']}).encode()
        files['desktop-setup.ps1'] = render('desktop-setup.ps1.tpl', {
            'WIDTH': desktop['width'], 'HEIGHT': desktop['height']}).encode()
    if windows:
        files['account-password'] = ('Qemu!' + secrets.token_urlsafe(24)).encode()
        files['bootstrap.ps1'] = render('bootstrap.ps1.tpl', values).encode()
        files['verify.ps1'] = render('verify.ps1.tpl', values).encode()
        files['appium.ps1'] = render('appium.ps1.tpl', values).encode()
    else:
        files['bootstrap.sh'] = render('bootstrap.sh.tpl', values).encode()
        files['appium.service'] = render('appium.service.tpl', values).encode()
        files['appium.plist'] = render('appium.plist.tpl', values).encode()
        files['verify.py'] = render('verify.py.tpl', values).encode()
        if config['os'] == 'macos':
            files['macos-autologin.cjs'] = render('macos-autologin.cjs.tpl', {}).encode()
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
    requirements = record_for(config)
    if requirements is not None:
        config = {**config, 'desktop': requirements['desktop'], 'runtime_requirements': requirements}
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
        # Binary runtimes live in payload.zip on the seed disk. Feeding hundreds
        # of MB through YAML/base64 can stall cloud-init before SSH even starts.
        entries = [{'path': '/opt/qemu-guests/seed-bootstrap.sh', 'encoding': 'b64',
                    'content': base64.b64encode(render('seed-bootstrap.sh.tpl', {}).encode()).decode(),
                    'permissions': '0600'}]
        user = {'name': config['ssh_user'], 'shell': '/bin/bash', 'sudo': 'ALL=(ALL) NOPASSWD:ALL',
                'ssh_authorized_keys': [Path(config['access_key'] + '.pub').read_text().strip()]}
        cloud = {'users': [user], 'ssh_pwauth': False, 'packages': ['openssh-client', 'openssh-server', 'python3'],
                 'write_files': entries, 'runcmd': [['bash', '/opt/qemu-guests/seed-bootstrap.sh']]}
        if config.get('graphical'):
            cloud['packages'] += ['xfce4', 'lightdm', 'lightdm-gtk-greeter', 'xserver-xorg']
            cloud['runcmd'].extend([['systemctl', 'set-default', 'graphical.target'], ['systemctl', 'start', 'lightdm']])
        if 'desktop' in config:
            from guest_desktop import LINUX_PACKAGES
            cloud['packages'] += LINUX_PACKAGES + config['desktop']['packages']
            cloud['write_files'].append({'path': '/etc/lightdm/lightdm.conf.d/60-test-autologin.conf',
                'permissions': '0644', 'content': '[Seat:*]\nautologin-user=' + config['ssh_user'] + '\nautologin-user-timeout=0\nautologin-session=xfce\nuser-session=xfce\n'})
        (directory / 'user-data').write_text('#cloud-config\n' + json.dumps(cloud), encoding='utf-8')
        (directory / 'meta-data').write_text(json.dumps({'instance-id': config['name'], 'local-hostname': config['name']}), encoding='utf-8')
    elif config['os'] == 'windows':
        image = config.get('windows_image', 'Windows 10 Pro')
        (directory / 'Autounattend.xml').write_text(render('Autounattend.xml.tpl', {
            'USER': config['ssh_user'], 'PASSWORD': files['account-password'].decode(),
            'IMAGE': escape(image),
        }), encoding='utf-8')
    elif config['os'] == 'macos':
        settings = config['macos']
        (directory / 'bootstrap.pkg').write_bytes(Path(settings['bootstrap_package']).read_bytes())
        (directory / 'macos-target-disk.awk').write_text(render('macos-target-disk.awk.tpl', {}),
                                                       encoding='utf-8', newline='\n')
        (directory / 'macos-install.sh').write_text(render('macos-install.sh.tpl', {
            'TARGET_DISK': shlex.quote(settings['target_disk']),
            'INSTALLER_APP': shlex.quote(settings['installer_app']),
        }), encoding='utf-8', newline='\n')
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
