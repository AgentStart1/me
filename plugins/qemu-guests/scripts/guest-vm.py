#!/usr/bin/env python3
"""Supervised, concurrent Appium test VMs; the Alpine Docker backend is independent."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid

from guest_config import load, verify_inputs
from guest_seed import prepare_seed
from guest_registry import register
from process_identity import identity, owns_listeners, terminate, write_record
from resource_ownership import Cancelled, defer_cancellation, signals


def read_record(home):
    try:
        return json.loads((home / 'running.json').read_text())
    except FileNotFoundError:
        return None


def alive(record):
    return identity(record['pid']) == record['identity']


def process_environment(config):
    if config.get('qemu_runtime') == 'reims-whpx':
        # The qualified Windows path presents through QMP; SDL is not qualified.
        return {**os.environ, 'REIMS_VGPU_WINDOW': '0'}
    return None


def arguments(config, home, installing, first_boot=True):
    disk = str(home / 'disk.qcow2').replace(',', ',,')
    port = config['ssh_port']
    hardware = config['hardware_args'] or [
        '-drive', f'file={disk},format=qcow2,if=ide',
        '-netdev', f'user,id=worknet,hostfwd=tcp:127.0.0.1:{port}-:22',
        '-device', 'e1000,netdev=worknet']
    hardware = [v.replace('{state}', str(home)).replace('{disk}', disk).replace('{ssh_port}', str(port))
                for v in hardware]
    command = [config.get('qemu', 'qemu-system-x86_64'), '-name', config['name'],
               '-m', str(config['memory']), '-smp', str(config['cpus']),
               *hardware, '-display', 'none',
               '-serial', 'file:' + str(home / 'console.log'), '-monitor', 'stdio',
               *config['qemu_args']]
    if config['graphical'] or config['os'] == 'macos':
        command += ['-qmp', f'tcp:127.0.0.1:{config["qmp_port"]},server=on,wait=off']
    if installing:
        if config.get('install_reboots', 0):
            command += ['-no-reboot']
        seed = str(home / 'seed.iso').replace(',', ',,')
        if config.get('installer_iso'):
            media = config['installer_iso'].replace(',', ',,')
            if config['os'] == 'macos':
                # createinstallmedia/UDTO is a partitioned Apple disk image,
                # not ISO9660 optical media. OpenCore must remain the bootloader.
                command += ['-drive', f'file={media},format=raw,if=none,readonly=on,id=macos-installer',
                            '-device', 'usb-storage,drive=macos-installer', '-boot', 'order=c']
            else:
                # Later Windows installer reboots must select the disk.
                command += ['-drive', f'file={media},format=raw,media=cdrom,readonly=on,index=2',
                            '-boot', 'order=c,once=d' if first_boot else 'order=c']
        command += ['-drive', f'file={seed},format=raw,media=cdrom,readonly=on,index=3']
        command += [v.replace('{state}', str(home)).replace('{seed}', str(home / 'seed'))
                    for v in config['install_args']]
    return command


def acceptance(config, home):
    if config['acceptance']:
        return [v.replace('{state}', str(home)).replace('{ssh_port}', str(config['ssh_port']))
                for v in config['acceptance']]
    if config['os'] == 'macos':
        remote = '/bin/bash /opt/qemu-guests/verify-macos.sh'
    elif config['os'] == 'ubuntu':
        remote = 'sudo python3 /opt/qemu-guests/verify.py'
        if not (home / 'installed.json').exists():
            remote = ('status=$(sudo cloud-init status --format=json) && printf \'%s\' "$status" | '
                      'python3 -c "import json,sys; sys.exit(json.load(sys.stdin)[\'status\'] != \'done\')" && '
                      + remote)
    else:
        remote = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:/ProgramData/qemu-guests/verify.ps1'
    return ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=accept-new',
            '-o', 'UserKnownHostsFile=' + str(home / 'known_hosts'), '-o', 'ConnectTimeout=3',
            '-i', config['access_key'], '-p', str(config['ssh_port']),
            config['ssh_user'] + '@127.0.0.1', remote]


def installation_record(config):
    record = {'os': config['os'], 'media_sha256': config['media_sha256']}
    if config.get('qemu_runtime') == 'virgl-whpx':
        record['graphics_backend'] = 'virgl'
    return record


def initialize(config, home):
    verify_inputs(config)
    if config['os'] == 'windows':
        from windows_image import editions, select
        config = {**config, 'windows_image': select(editions(config['installer_iso']),
                  config.get('windows_image', 'Windows 10 Pro'), config['graphical'])}
    if (home / 'disk.qcow2').exists() or (home / 'seed').exists():
        raise ValueError('Disk/seed already exists; preserve incomplete installation for inspection. Use run to resume.')
    image_tool = config.get('qemu_img', 'qemu-img')
    if config.get('base_image'):
        subprocess.run([image_tool, 'convert', '-O', 'qcow2', config['base_image'], str(home / 'disk.qcow2')], check=True)
        subprocess.run([image_tool, 'resize', str(home / 'disk.qcow2'), config['disk_size']], check=True)
    else:
        subprocess.run([image_tool, 'create', '-f', 'qcow2', str(home / 'disk.qcow2'), config['disk_size']], check=True)
    prepare_seed(config, home / 'seed')
    if 'runtime_requirements' in config:
        from initialization_snapshot import record_for
        write_record(home / 'runtime-requirements.json', record_for(config))
    write_record(home / 'installation.json', installation_record(config))


def private_home(home):
    """Restrict a newly created state directory before staging private seed files."""
    home.parent.mkdir(parents=True, exist_ok=True)
    try:
        home.mkdir(mode=0o700)
    except FileExistsError:
        return  # Existing state belongs to its operator; never rewrite its ACL.
    if os.name == 'nt':
        try:
            output = subprocess.check_output(['whoami', '/user', '/fo', 'csv', '/nh'])
            sid = re.search(rb'S-1-5-[0-9-]+', output)
            if sid is None:
                raise RuntimeError('Cannot identify Windows account for private state ACL')
            subprocess.run(['icacls', str(home), '/inheritance:r', '/grant:r',
                            '*' + sid.group().decode() + ':(OI)(CI)F',
                            '*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F'],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except (OSError, RuntimeError, subprocess.SubprocessError):
            home.rmdir()  # Only our still-empty directory; no seed has been written.
            raise


def supervise(config, home, installing):
    """Hold a per-VM lease for the entire foreground session; never adopt a process."""
    with defer_cancellation():
        private_home(home)
    lease = home / 'session.lock'
    child = None
    record = None
    token = uuid.uuid4().hex
    acquired = False
    try:
        with defer_cancellation():
            lease.mkdir()
            acquired = True
            write_record(lease / 'owner.json', {'pid': os.getpid(), 'identity': identity(os.getpid()), 'token': token})
        existing = read_record(home)
        if existing:
            raise RuntimeError('Retained VM ownership record; inspect status before recovery')
        register(config, home)
        if installing:
            initialize(config, home)
        else:
            if not (home / 'disk.qcow2').is_file() or not (home / 'installation.json').is_file():
                raise ValueError('No initialized disk; run install first')
            installed = json.loads((home / 'installation.json').read_text())
            if installed != installation_record(config):
                raise ValueError('OS/media/graphics changed; use a new state_dir')
        # Interrupted installations keep their seed attached when resumed.
        boot_install = not (home / 'installed.json').exists()
        with open(home / 'qemu.log', 'ab') as qemu_log:
            with defer_cancellation():
                child = subprocess.Popen(arguments(config, home, boot_install, first_boot=installing), stdin=subprocess.PIPE,
                                         stdout=qemu_log, stderr=qemu_log, env=process_environment(config),
                                         start_new_session=os.name != 'nt',
                                         creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
                native = identity(child.pid)
                if native is None:
                    raise RuntimeError('QEMU exited during launch; see qemu.log')
                record = {'pid': child.pid, 'identity': native, 'token': token, 'phase': 'booting'}
                write_record(home / 'running.json', record)
            deadline = time.monotonic() + config['timeout']
            macos_driver = None
            if config['os'] == 'macos' and boot_install:
                from macos_install import RecoveryInstaller
                macos_driver = RecoveryInstaller(config, home, record)
            next_probe = 0
            next_machine_probe = 0
            stopping = False
            accepted = False
            reboot_count = 0
            while True:
                request_path = home / ('stop-' + token + '.json')
                exited = child.poll() is not None
                if exited:
                    stopping = stopping or request_path.exists()
                    if (not stopping and not accepted and child.returncode == 0 and boot_install
                            and record['phase'] == 'booting'
                            and reboot_count < config.get('install_reboots', 0)
                            and time.monotonic() < deadline):
                        # Explicit installer-only cold boot budget avoids WHPX
                        # reset failures. Never retry crashes or boot installer
                        # media ahead of the retained disk after the first boot.
                        child.stdin.close()
                        with defer_cancellation():
                            child = subprocess.Popen(arguments(config, home, True, first_boot=False), stdin=subprocess.PIPE,
                                stdout=qemu_log, stderr=qemu_log, env=process_environment(config),
                                start_new_session=os.name != 'nt',
                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
                            record = {**record, 'pid': child.pid, 'identity': identity(child.pid)}
                            if record['identity'] is None:
                                raise RuntimeError('QEMU exited during installer cold boot')
                            write_record(home / 'running.json', record)
                        reboot_count += 1
                        next_probe = 0
                        print(f'Installer cold boot {reboot_count}; disk retained and acceleration unchanged.', flush=True)
                        continue
                    break
                if request_path.exists():
                    request = json.loads(request_path.read_text())
                    if request.get('force'):
                        stopping = True
                        terminate(record)
                        child.wait(timeout=15)
                        break
                    if not stopping:
                        child.stdin.write(b'system_powerdown\n')
                        child.stdin.flush()
                        stopping = True
                        record = {**record, 'phase': 'stopping'}
                        write_record(home / 'running.json', record)
                        print('ACPI shutdown requested; use stop --force if the guest cannot shut down.', flush=True)
                if not stopping and not accepted and time.monotonic() > deadline:
                    raise RuntimeError('Guest readiness timed out; installation is retained for run/resume')
                if (not stopping and config.get('qmp_port') and time.monotonic() >= next_machine_probe
                        and owns_listeners(child.pid, {config['qmp_port']})):
                    from guest_screen import Qmp
                    try:
                        client = Qmp(config['qmp_port'])
                        try:
                            machine = client.execute('query-status')
                        finally:
                            client.close()
                        phase = 'paused' if not machine['running'] else 'booting' if record['phase'] == 'paused' else record['phase']
                        if phase != record['phase']:
                            record = {**record, 'phase': phase}
                            write_record(home / 'running.json', record)
                    except (OSError, ValueError, RuntimeError):
                        pass  # A transient QMP failure does not establish a new VM state.
                    next_machine_probe = time.monotonic() + 3
                if not stopping and record['phase'] == 'booting':
                    if macos_driver is not None:
                        macos_driver.tick()
                    if time.monotonic() >= next_probe and owns_listeners(child.pid, {config['ssh_port']}):
                        try:
                            with open(home / 'acceptance.log', 'ab') as log:
                                result = subprocess.run(acceptance(config, home), stdout=log, stderr=log, timeout=15)
                            if result.returncode == 0 and child.poll() is None and alive(record):
                                record = {**record, 'phase': 'ready'}
                                accepted = True
                                write_record(home / 'running.json', record)
                                write_record(home / 'installed.json', {'os': config['os']})
                                print('Guest ready; SSH and Appium acceptance passed. Session remains supervised.', flush=True)
                        except subprocess.TimeoutExpired:
                            pass
                        next_probe = time.monotonic() + 3
                time.sleep(.2)
            if child.returncode and not stopping:
                raise RuntimeError('QEMU exited unsuccessfully; inspect qemu.log')
            if record['phase'] != 'ready' and not stopping:
                raise RuntimeError('Guest exited before acceptance; installation is retained')
    finally:
        # Forced cancellation stops only this session's native QEMU. Failed cleanup
        # retains the lock and process record rather than permitting a second writer.
        with defer_cancellation():
            if child is not None:
                if child.poll() is None:
                    if record is not None:
                        terminate(record)
                    else:
                        child.kill()
                child.wait(timeout=15)
            if acquired:
                if record is not None:
                    (home / 'running.json').unlink(missing_ok=True)
                    (home / ('stop-' + token + '.json')).unlink(missing_ok=True)
                (lease / 'owner.json').unlink(missing_ok=True)
                lease.rmdir()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'run', 'stop', 'status', 'plan'])
    parser.add_argument('profile', type=Path)
    parser.add_argument('--force', action='store_true', help='force stop the owned guest process')
    parser.add_argument('--requirements', type=Path, help='Portable project desktop runtime requirements')
    args = parser.parse_args(argv)
    config = load(args.profile)
    home = Path(config['state_dir'])
    if args.requirements:
        from test_requirements import apply
        config = apply(config, args.requirements)
        if args.action == 'run':
            recorded = home / 'runtime-requirements.json'
            if not recorded.exists() or json.loads(recorded.read_text())['sha256'] != config['runtime_requirements']['sha256']:
                raise ValueError('Existing VM was not initialized with these runtime requirements; use a new state directory')
    elif (home / 'runtime-requirements.json').exists():
        requirements = json.loads((home / 'runtime-requirements.json').read_text())
        config = {**config, 'desktop': requirements['desktop'], 'runtime_requirements': requirements}
    if args.action == 'plan':
        from whpx_runtime import prepare
        config = prepare(config, build_runtime=False)
        print(json.dumps(arguments(config, home, True), indent=2))
        return
    if args.action in {'status', 'stop'}:
        record = read_record(home)
        try:
            running = bool(record and alive(record))
            owner_path = home / 'session.lock' / 'owner.json'
            owner = json.loads(owner_path.read_text()) if owner_path.exists() else None
            supervised = bool(owner and alive(owner) and record and owner['token'] == record['token'])
        except (OSError, ValueError):
            if args.action == 'stop':
                raise RuntimeError('Process inspection unknown; refusing stop')
            print(json.dumps({'name': config['name'], 'phase': 'unknown'}))
            return
        if args.action == 'status':
            phase = record['phase'] if running and supervised else 'recovery-required' if record or (home / 'session.lock').exists() else 'stopped'
            print(json.dumps({'name': config['name'], 'phase': phase, 'pid': record['pid'] if running else None}))
        else:
            if not running:
                raise RuntimeError('No verified running guest; retained state requires inspection')
            if not supervised:
                raise RuntimeError('Supervisor is gone; inspect retained process/lease before manual recovery')
            write_record(home / ('stop-' + record['token'] + '.json'), {'force': args.force})
            print('Stop requested; the supervising session will report completion.')
        return
    from whpx_runtime import prepare
    config = prepare(config)
    def cancel(number, _frame):
        raise Cancelled(number)
    for number in signals():
        signal.signal(number, cancel)
    supervise(config, home, args.action == 'install')


if __name__ == '__main__':
    try:
        main()
    except Cancelled as error:
        sys.exit(error.status)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'Guest operation failed: {error}', file=sys.stderr)
        sys.exit(1)
