#!/usr/bin/env python3
"""Restore a prepared Intel macOS test desktop and qualify actual native UI APIs."""
import argparse
import hashlib
import json
import plistlib
from pathlib import Path
import re
import shlex
import socket
import subprocess
import sys
import time
import traceback

from guest_config import load as guest_config
from macos_console import MacConsole
from macos_desktop_plan import load as desktop_plan
from macos_native import NativeClient, NativeError, qualify
from macos_permissions import PermissionRepair
from macos_wda import listener as wda_process, restart as restart_wda
from macos_windows import inventory as finder_windows
from process_identity import identity, owns_listeners, write_record
from test_cli_lifecycle import CliSignalScope
from test_cancellation import is_cancellation
from test_cleanup_diagnostics import report_cleanup
from test_environment_owner import TestEnvironmentOwner
from test_guest_transport import GuestTransport

MAC2_PREFLIGHT = (Path(__file__).resolve().parents[1] /
                 'templates/guests/verify-mac2.cjs.tpl').read_bytes()


def verified_record(config):
    home = Path(config['state_dir'])
    record = json.loads((home / 'running.json').read_text())
    supervisor = json.loads((home / 'session.lock/owner.json').read_text())
    ports = {config['ssh_port'], config['qmp_port']}
    if (record.get('identity') is None or supervisor.get('identity') is None or
            identity(record['pid']) != record['identity'] or
            identity(supervisor['pid']) != supervisor['identity'] or
            record['token'] != supervisor['token'] or not owns_listeners(record['pid'], ports)):
        raise RuntimeError('Guest ownership or loopback listeners cannot be verified')
    return record


def shell(transport, command, *, data=None, timeout=120):
    return transport.run([*transport.ssh(), transport.target, command], timeout=timeout,
                         stdin_data=data, operation='macOS desktop operation')


def prepare(transport, config, plan):
    destination = '/Users/' + config['ssh_user'] + '/.qemu-guests-desktop-inputs'
    shell(transport, 'umask 077; mkdir -p ' + shlex.quote(destination))
    for index, item in enumerate(plan.files, 1):
        remote = destination + '/' + item.name
        existing = shell(transport, 'if [ -f ' + shlex.quote(remote) + ' ]; then shasum -a 256 ' +
                         shlex.quote(remote) + '; fi').decode().split()
        if not existing or existing[0] != item.sha256:
            known = str(Path(config['state_dir']) / 'known_hosts')
            transport.run(['scp', '-q', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                           '-o', 'UserKnownHostsFile=' + known, '-i', config['access_key'], '-P',
                           str(config['ssh_port']), str(item.source), transport.target + ':' + remote],
                          timeout=3600, operation='prepared artifact transfer')
            digest = shell(transport, 'shasum -a 256 ' + shlex.quote(remote)).decode().split()[0]
            if digest != item.sha256:
                raise ValueError('Transferred desktop artifact checksum mismatch')
        print(f'Prepared desktop artifact {index}/{len(plan.files)} verified.', flush=True)
    if plan.setup_script is not None:
        script = destination + '/runtime-setup.sh'
        shell(transport, 'umask 077; cat > ' + shlex.quote(script), data=plan.setup_script)
        print('Installing supplied desktop runtime and session configuration.', flush=True)
        # sudo consumes one line. The supplied, reviewed setup script may read
        # one further line to restore its existing automatic-login credential.
        shell(transport, "sudo -k -S -p '' /bin/bash " + shlex.quote(script) + ' ' + shlex.quote(config['ssh_user']),
              data=((plan.password + '\n') * 2).encode(), timeout=3600)


def signing_fingerprint(transport, plan):
    identities = []
    for target in plan.permissions:
        # Check the complete bundle, then bind the grant to reviewed main-code identity.
        output = shell(transport, 'codesign --verify --deep ' + shlex.quote(target.path) +
                        ' && codesign -d --verbose=4 ' + shlex.quote(target.path) + ' 2>&1').decode()
        identifier = re.search(r'^Identifier=(.+)$', output, re.MULTILINE)
        cdhash = re.search(r'^CDHash=([a-f0-9]+)$', output, re.MULTILINE)
        if not identifier or not cdhash or identifier[1] != target.bundle_id or cdhash[1] != target.cdhash:
            raise ValueError('Prepared application signing identity does not match the reviewed manifest')
        identities.append((target.bundle_id, target.cdhash))
    return hashlib.sha256(json.dumps([plan.expected_build, identities]).encode()).hexdigest()


def wda_listener(transport, plan):
    return wda_process(lambda cmd, **kwargs: shell(transport, cmd, **kwargs), plan.wda_url)


def wait_wda(transport, plan, owner, previous_pid=None):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        owner.checkpoint()
        try:
            if previous_pid is not None and wda_listener(transport, plan) == previous_pid:
                time.sleep(.5)
                continue
            value = json.loads(shell(transport, 'curl --noproxy 127.0.0.1 -fsS ' +
                                    shlex.quote(plan.wda_url.rstrip('/') + '/status'), timeout=10))
            if value.get('value', {}).get('ready'):
                return
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            pass
        time.sleep(1)
    raise TimeoutError('Prepared WDA endpoint did not become ready; no guest build was attempted')


def endpoint(transport):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    transport.forward(['-L', f'127.0.0.1:{port}:127.0.0.1:4723'])
    return f'http://127.0.0.1:{port}'


def run(action, config, plan, force_repair=False, owner=None):
    if force_repair and action != 'reconcile':
        raise ValueError('Permission repair is available only during reconcile')
    if config['os'] != 'macos' or not config['graphical']:
        raise ValueError('A graphical macOS guest is required')
    home = Path(config['state_dir'])
    if not (home / 'known_hosts').is_file():
        raise ValueError('Authenticated guest host keys must be pinned before desktop provisioning')
    output = home / 'macos-desktop'
    output.mkdir(mode=0o700, exist_ok=True)
    state = output / 'state.json'
    owner = TestEnvironmentOwner(home) if owner is None else owner
    stage = 'guest-reservation'

    def publish_failure(failure):
        write_record(state, {'phase': 'recovery-required' if owner.cleanup_uncertain else 'failed',
                             'stage': stage, 'error_type': type(failure).__name__, 'plan_sha256': plan.digest})
        if not is_cancellation(failure):
            (output / 'operation-error.log').write_text(''.join(traceback.format_exception(failure)), encoding='utf-8')

    def publish(error):
        if error is not None:
            publish_failure(error)
            return
        try:
            final_record = verified_record(config)
            if any(final_record[key] != record[key] for key in ('pid', 'identity', 'token')):
                raise RuntimeError('Guest process changed during desktop qualification')
            receipt = {'phase': 'prepared' if action == 'prepare' else 'ready', 'plan_sha256': plan.digest,
                       'build': build, 'guest_identity': record['identity'], **result}
            write_record(state, receipt)
        except BaseException as failure:
            publish_failure(failure)
            raise

    with owner:
        if owner.path is None:
            owner.acquire_lease(home)
        owner.on_drained(publish)
        write_record(state, {'phase': 'checking', 'plan_sha256': plan.digest})
        stage = 'guest-identity'
        record = verified_record(config)
        transport = GuestTransport(config, output)
        owner.callback(transport.close)
        build = shell(transport, 'sw_vers -buildVersion').decode().strip()
        architecture = shell(transport, 'uname -m').decode().strip()
        if build != plan.expected_build or architecture != 'x86_64':
            raise ValueError('Guest OS build/architecture does not match the prepared desktop manifest')
        prepared_path = output / 'prepared.json'
        prepared = json.loads(prepared_path.read_text()) if prepared_path.exists() else {}
        if action != 'verify' and prepared.get('plan_sha256') != plan.digest:
            stage = 'prepared-runtime'
            prepare(transport, config, plan)
            write_record(prepared_path, {'plan_sha256': plan.digest, 'build': build})
        if action != 'verify':
            # Scope idle policy to this dedicated account. This does not
            # bypass an existing lock or change password/security policy.
            shell(transport, '/usr/bin/defaults -currentHost write com.apple.screensaver idleTime -int 0')
        if action == 'prepare':
            # This is an asset/session preparation milestone, never desktop readiness.
            result = {'prepared': True}
        else:
            stage = 'desktop-qualification'
            result = verify_desktop(action, config, plan, owner, transport, output, state, force_repair)
    print('macOS desktop prepared.' if action == 'prepare' else
          'macOS desktop ready: native input, window geometry and supplied checks passed.', flush=True)


def refresh_wda(transport, config, plan, owner):
    previous_pid = wda_listener(transport, plan)
    restart_wda(lambda cmd, **kwargs: shell(transport, cmd, **kwargs), config, plan, owner)
    wait_wda(transport, plan, owner, previous_pid=previous_pid)


def verify_desktop(action, config, plan, owner, transport, output, state, force_repair):
    console_user = shell(transport, 'stat -f %Su /dev/console').decode().strip()
    if console_user != config['ssh_user']:
        raise RuntimeError('Expected automatic desktop login has not completed')
    qualify_console(action, config, plan, owner, transport, output)
    shell(transport, 'launchctl print gui/$(id -u)/com.me.qemu-guests.appium >/dev/null')
    shell(transport, '/opt/qemu-guests/appium/node -', data=MAC2_PREFLIGHT)
    fingerprint = signing_fingerprint(transport, plan)
    shell(transport, 'launchctl print gui/$(id -u)/' + plan.wda_service + ' >/dev/null')
    wait_wda(transport, plan, owner)
    if action == 'reconcile':
        refresh_wda(transport, config, plan, owner)
    native = NativeClient(endpoint(transport), plan.wda_url, owner, output,
                          window_inventory=lambda: finder_windows(lambda cmd, **kwargs: shell(transport, cmd, **kwargs)))
    native.wait_ready()
    missing_accessibility = False
    try:
        result = qualify(native, config['ssh_user'], output)
    except NativeError as error:
        if action != 'reconcile' or not error.accessibility_required:
            raise
        missing_accessibility = True
    if missing_accessibility or force_repair:
        write_record(state, {'phase': 'repairing-permissions', 'plan_sha256': plan.digest})
        console = MacConsole(config['qmp_port'], output, config['macos']['tesseract'], owner)
        try:
            PermissionRepair(native, console, lambda cmd: shell(transport, cmd), plan.password,
                             authorization_identity=lambda: authorization_identity(transport, config['ssh_user'])).repair(
                plan.permissions, reregister=missing_accessibility)
        finally:
            owner.cleanup(console.close)
        # WDA caches AX trust. A ready response from the old runner does not
        # establish that newly granted permissions are active in a fresh process.
        refresh_wda(transport, config, plan, owner)
        result = qualify(native, config['ssh_user'], output)
    for name, argv in plan.checks:
        data = shell(transport, shlex.join(argv), timeout=120)
        (output / (name + '.log')).write_bytes(data)
    return {'signing_sha256': fingerprint, 'native': result, 'checks': [name for name, _ in plan.checks]}


def require_unlocked_console(transport, user):
    locked, _session = console_state(transport, user)
    if locked:
        raise RuntimeError('Desktop is locked; reconcile the dedicated test account before verification')


def console_state(transport, user):
    data = plistlib.loads(shell(transport, '/usr/sbin/ioreg -n Root -d1 -a'))
    if isinstance(data, list) and len(data) == 1:
        data = data[0]
    if not isinstance(data, dict) or type(data.get('IOConsoleLocked')) is not bool:
        raise RuntimeError('Cannot verify graphical session lock state')
    sessions = [value for value in data.get('IOConsoleUsers', [])
                if value.get('kCGSSessionOnConsoleKey') is True and value.get('kCGSSessionUserNameKey') == user]
    if len(sessions) != 1:
        raise RuntimeError('Desktop console account is ambiguous')
    locked = data['IOConsoleLocked'] or sessions[0].get('CGSSessionScreenIsLocked') is True
    return locked, sessions[0]


def authorization_identity(transport, user):
    locked, session = console_state(transport, user)
    pid = session.get('kCGSSessionSecureInputPID')
    if locked or type(pid) is not int or pid <= 0:
        raise RuntimeError('System authorization password focus cannot be verified')
    uid = shell(transport, 'id -u').decode().strip()
    record = shell(transport, f'ps -ww -p {pid} -o uid= -o lstart= -o comm=').decode().strip()
    executables = (
        '/System/Applications/System Settings.app/Contents/MacOS/System Settings',
        '/System/Library/Frameworks/Security.framework/Versions/A/MachServices/'
        'SecurityAgent.bundle/Contents/MacOS/SecurityAgent',
    )
    if (not uid.isdigit() or record.split(None, 1)[:1] != [uid]
            or not any(record.endswith(' ' + executable) for executable in executables)):
        raise RuntimeError('Secure input does not belong to a reviewed system authorization process')
    return pid, record


def qualify_console(action, config, plan, owner, transport, output):
    user = config['ssh_user']
    locked, session = console_state(transport, user)
    if not locked:
        return
    if action != 'reconcile':
        raise RuntimeError('Desktop is locked; reconcile the dedicated test account before verification')
    pid = session.get('kCGSSessionSecureInputPID')
    label = session.get('kCGSessionLongUserNameKey')
    if (session.get('CGSSessionScreenIsLocked') is not True or type(pid) is not int or pid <= 0
            or not isinstance(label, str) or not label):
        raise RuntimeError('System login target cannot be verified')
    executable = shell(transport, f'ps -ww -p {pid} -o comm=').decode().strip()
    if executable != '/System/Library/CoreServices/loginwindow.app/Contents/MacOS/loginwindow':
        raise RuntimeError('Secure input does not belong to the system loginwindow')
    console = MacConsole(config['qmp_port'], output, config['macos']['tesseract'], owner)
    try:
        def confirm_target():
            still_locked, current = console_state(transport, user)
            if (not still_locked or current.get('kCGSSessionSecureInputPID') != pid
                    or current.get('kCGSessionLongUserNameKey') != label):
                raise RuntimeError('System login target changed before credential entry')
        console.unlock(label, plan.password, confirm_target)
        # Cold login can take longer than 30 seconds on the four-vCPU guest.
        # Wait for the OS state transition without submitting a second password.
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            owner.checkpoint()
            locked, _session = console_state(transport, user)
            if not locked:
                return
            time.sleep(.5)
        raise RuntimeError('Configured account login did not unlock the console; no credential retry was attempted')
    finally:
        owner.cleanup(console.close)



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'reconcile', 'verify'])
    parser.add_argument('profile', type=Path)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--repair-permissions', action='store_true')
    args = parser.parse_args()
    with CliSignalScope() as cli:
        owner = TestEnvironmentOwner(cancellation=cli.cancellation)

        def operation():
            run(args.action, guest_config(args.profile), desktop_plan(args.plan), args.repair_permissions, owner=owner)
            return 0

        cli.execute(operation)
        result = cli.result(owner)
        report_cleanup(result.cleanup, sys.stderr)
        if isinstance(result.error, Exception) and not is_cancellation(result.error):
            print('macOS desktop operation failed; inspect its private state and diagnostics.', file=sys.stderr)
        return 1 if result.status is None else result.status


if __name__ == '__main__':
    sys.exit(main())
