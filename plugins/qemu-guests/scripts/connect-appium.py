#!/usr/bin/env python3
"""Keep an authenticated loopback Appium tunnel open until interrupted."""
import argparse
import subprocess
from pathlib import Path
from guest_config import load


def command(config):
    known_hosts = Path(config['state_dir']) / 'known_hosts'
    pinned = ['-o', 'UserKnownHostsFile=' + str(known_hosts), '-o', 'StrictHostKeyChecking=yes'] if known_hosts.exists() else []
    return ['ssh', '-N', '-T', '-o', 'BatchMode=yes', '-o', 'ExitOnForwardFailure=yes',
            '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
            '-i', config['access_key'], '-p', str(config['ssh_port']), *pinned,
            '-L', f'127.0.0.1:{config["appium"]["host_port"]}:127.0.0.1:4723',
            config['ssh_user'] + '@127.0.0.1']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile')
    args = parser.parse_args()
    config = load(args.profile)
    print(f'Appium endpoint: http://127.0.0.1:{config["appium"]["host_port"]}', flush=True)
    # OpenSSH verifies/pins the guest host key using the operator known_hosts.
    raise SystemExit(subprocess.call(command(config)))
