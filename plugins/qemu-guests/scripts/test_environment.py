#!/usr/bin/env python3
"""Run a host command with configured Docker and transparent guest Appium services."""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import urllib.request

from guest_config import load as guest_config
from guest_registry import entries, state
from process_identity import owns_listeners
from test_command_tree import TestCommandTree as CommandTree
from test_appium_proxy import AppiumProxy
from test_environment_config import load
from test_guest_transport import GuestTransport
from test_linux_transport import LinuxTransport
from test_environment_owner import TestEnvironmentOwner
from test_cleanup_diagnostics import report_cleanup
from test_cli_lifecycle import CliSignalScope


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def guest_lease(home):
    return TestEnvironmentOwner(home)


def run(config, command, owner=None):
    if not command:
        raise ValueError('A host test command is required')
    environment = {**os.environ, **config['environment']}
    owner = TestEnvironmentOwner() if owner is None else owner
    with owner:
        owner.checkpoint()
        if 'appium' in config:
            guest = guest_config(config['appium']['guest'])
            if 'requirements' in config:
                from test_requirements import load as load_requirements
                required = load_requirements(config['requirements'], guest['os'])
                recorded = Path(guest['state_dir']) / 'runtime-requirements.json'
                if not recorded.exists() or json.loads(recorded.read_text())['sha256'] != required['sha256']:
                    raise ValueError('Guest must be initialized with the project runtime requirements before testing')
            if guest['os'] not in {'windows', 'ubuntu'}:
                raise ValueError('Transparent launch requires a Windows or Linux guest')
            if guest['os'] == 'windows' and os.name != 'nt':
                raise ValueError('Transparent Windows launches currently require a Windows host')
            item = next((item for item in entries() if Path(item['state_dir']) == Path(guest['state_dir'])), None)
            phase, record = state(item) if item else ('unknown', None)
            if phase != 'ready' or not owns_listeners(record['pid'], [guest['ssh_port']]):
                raise RuntimeError('The configured work guest must already be ready and own its SSH listener')
            owner.acquire_lease(guest['state_dir'])
            owner.checkpoint()
            cache = config['workspace'] / 'build/test-env'
            cache.mkdir(parents=True, exist_ok=True)
            temporary = owner.enter_context(tempfile.TemporaryDirectory(prefix='session-', dir=cache))
            if guest['os'] == 'ubuntu':
                runtime = os.environ.get('TEST_ENV_LINUX_RUNTIME')
                transport = LinuxTransport(guest, temporary, runtime)
            else:
                transport = GuestTransport(guest, temporary)
            owner.callback(transport.close)
            owner.checkpoint()
            port = free_port()
            transport.forward(['-L', f'127.0.0.1:{port}:127.0.0.1:{getattr(transport, "appium_port", 4723)}'])
            owner.checkpoint()
            upstream = f'http://127.0.0.1:{port}'
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(upstream + '/status', timeout=10) as response:
                if not json.load(response)['value']['ready']:
                    raise RuntimeError('Guest Appium is not ready')
            owner.checkpoint()
            proxy = AppiumProxy(upstream, transport, config['appium'], config['workspace'])
            owner.callback(proxy.close)
            proxy.start()
            owner.checkpoint()
            environment.update(APPIUM_DESKTOP_SERVER_URL=proxy.url)
            print('Configured transparent guest Appium proxy; test commands and compilation stay on the host.', flush=True)
        if 'docker' in config:
            bash = shutil.which('bash')
            if not bash:
                raise RuntimeError('Bash is required by the Docker environment adapter')
            # Only the already-established backend environment adapter is invoked.
            # It retains its operation lease, Docker proxy, Ryuk, metrics and exit code.
            command = [bash, Path(__file__).with_name('run-test-env.sh').as_posix(), '--profile',
                       config['docker'].as_posix(), '--', *command]
        elif os.name == 'nt' and Path(shutil.which(command[0]) or command[0]).suffix.lower() not in {'.exe', '.com'}:
            bash = shutil.which('bash')
            if not bash:
                raise RuntimeError('Bash is required to preserve Windows host-command argument handling')
            command = [bash, '-c', 'exec "$@"', 'test-env', *command]
        tree = CommandTree()
        owner.callback(tree.stop)
        owner.checkpoint()
        child = tree.start(command, cwd=config['workspace'], env=environment)
        return owner.wait(child)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    with CliSignalScope() as cli:
        owner = TestEnvironmentOwner(cancellation=cli.cancellation)
        cli.execute(lambda: run(load(args.config), command, owner=owner))
        # Finalization runs outside the active execution exception handler.
        result = cli.result(owner)
        report_cleanup(result.cleanup, sys.stderr)
        if result.status is None:
            raise result.error
        return result.status


if __name__ == '__main__':
    raise SystemExit(main())
