#!/usr/bin/env python3
"""Opt-in real guest acceptance: concurrent QEMU, authenticated Appium readiness and graphical screens."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import importlib.util

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from guest_config import load

from guest_registry import entries, state
from guest_screen import capture


spec = importlib.util.spec_from_file_location('guest_vm', Path(__file__).resolve().parents[1] / 'scripts/guest-vm.py')
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)


def verify(config):
    item = next(item for item in entries() if Path(item['state_dir']) == Path(config['state_dir']))
    phase, record = state(item)
    if phase != 'ready':
        raise RuntimeError('Guest is not verified ready: ' + config['name'])
    result = subprocess.run(vm.acceptance(config, Path(config['state_dir'])), capture_output=True, timeout=15)
    if result.returncode:
        raise RuntimeError('Guest SSH/Appium acceptance failed: ' + config['name'])
    frame_bytes = len(base64.b64decode(capture(item['id'])['data'])) if config['graphical'] else None
    if state(item)[0] != 'ready':
        raise RuntimeError('Guest stopped during acceptance')
    return {'name': config['name'], 'os': config['os'], 'graphical': config['graphical'], 'pid': record['pid'],
            'appiumReady': True, 'screenPngBytes': frame_bytes}


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
    with ThreadPoolExecutor(max_workers=len(configs)) as pool:
        results = list(pool.map(verify, configs))
    if len({result['pid'] for result in results}) != len(results):
        raise RuntimeError('Guests do not have independent QEMU processes')
    args.report.write_text(json.dumps({'observedAt': datetime.now(timezone.utc).isoformat(),
                                      'concurrent': True, 'guests': results}, indent=2) + '\n')
    print('PASS: concurrent work guests, authenticated Appium readiness and graphical screen capture')


if __name__ == '__main__':
    main()
