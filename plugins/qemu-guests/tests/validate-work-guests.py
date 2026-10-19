#!/usr/bin/env python3
"""Opt-in real guest acceptance: concurrent QEMU, guest builds, API and TCP forwarding."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from guest_config import load
from guest_seed import render
from guest_registry import entries, state
from guest_screen import capture


def verify(job):
    config, port = job
    item = next(item for item in entries() if Path(item['state_dir']) == Path(config['state_dir']))
    phase, record = state(item)
    if phase != 'ready':
        raise RuntimeError('Guest is not verified ready: ' + config['name'])
    token = uuid.uuid4().hex
    script = render('acceptance.ps1.tpl' if config['os'] == 'windows' else 'acceptance.sh.tpl', {
        'TOKEN': token, 'PORT': port})
    command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-o', 'StrictHostKeyChecking=no',
               '-o', 'UserKnownHostsFile=' + os.devnull, '-i', config['access_key'], '-p', str(config['ssh_port']),
               config['ssh_user'] + '@127.0.0.1']
    if config['os'] == 'windows':
        command += ['powershell.exe -NoProfile -EncodedCommand ' + base64.b64encode(script.encode('utf-16le')).decode()]
        data = None
    else:
        command += ['sh -s']
        data = script.encode()
    result = subprocess.run(command, input=data, capture_output=True, timeout=600)
    if result.returncode or b'CLI_BUILD_API_PUBLISHED_PORT_OK' not in result.stdout:
        sys.stderr.buffer.write(result.stdout + result.stderr)
        raise RuntimeError('Guest Docker acceptance failed: ' + config['name'])
    frame_bytes = len(base64.b64decode(capture(item['id'])['data'])) if config['graphical'] else None
    if state(item)[0] != 'ready':
        raise RuntimeError('Guest stopped during acceptance')
    return {'name': config['name'], 'os': config['os'], 'graphical': config['graphical'], 'pid': record['pid'],
            'cliBuild': True, 'dockerApi': True, 'publishedTcp': True, 'screenPngBytes': frame_bytes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', action='append', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    configs = [load(path) for path in args.profile]
    if len(configs) < 2 or len({c['state_dir'] for c in configs}) != len(configs):
        parser.error('Select at least two independent running guests')
    for config in configs:
        item = next(item for item in entries() if item['state_dir'] == config['state_dir'])
        if state(item)[0] != 'ready':
            parser.error('All work guests must be ready before concurrent validation')
    jobs = [(config, config['backend']['publish_start'] + index) for index, config in enumerate(configs)]
    if any(port > config['backend']['publish_end'] for config, port in jobs):
        parser.error('Publish pools need one separate port for each concurrently tested guest')
    with ThreadPoolExecutor(max_workers=len(configs)) as pool:
        results = list(pool.map(verify, jobs))
    if len({result['pid'] for result in results}) != len(results):
        raise RuntimeError('Guests do not have independent QEMU processes')
    args.report.write_text(json.dumps({'observedAt': datetime.now(timezone.utc).isoformat(),
                                      'concurrent': True, 'guests': results}, indent=2) + '\n')
    print('PASS: concurrent work guests, in-guest context builds, Docker API, published TCP ports and graphical screen capture')


if __name__ == '__main__':
    main()
