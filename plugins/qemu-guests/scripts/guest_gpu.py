"""Validate the opt-in Ubuntu GPU session without exposing provider details to projects."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path('/opt/qemu-guests')


def renderer(output):
    match = re.search(r'^OpenGL renderer string:\s*(.+)$', output, re.M)
    name = match[1] if match else ''
    software = ('llvmpipe', 'softpipe', 'swiftshader', 'software', 'basic render', 'warp')
    if ('virgl' not in name.lower() or any(value in name.lower() for value in software)
            or not re.search(r'^\s*Accelerated:\s*yes\s*$', output, re.M)):
        raise ValueError('Hardware-accelerated VirGL renderer is required')
    return name


def process_start(pid):
    return Path(f'/proc/{pid}/stat').read_text().rsplit(') ', 1)[1].split()[19]


def verify_session(record, boot_id):
    if record['boot_id'] != boot_id or process_start(record['session_pid']) != record['session_start']:
        raise ValueError('GPU session receipt is stale')


def publish():
    expected = json.loads((ROOT / 'desktop.json').read_text())
    output = subprocess.check_output(['glxinfo', '-B'], text=True, timeout=15,
                                     env={**os.environ, 'LC_ALL': 'C'})
    name = renderer(output)
    dimensions = subprocess.check_output(['xdpyinfo'], text=True, timeout=10,
                                         env={**os.environ, 'LC_ALL': 'C'})
    size = re.search(r'dimensions:\s+(\d+)x(\d+)\s+pixels', dimensions)
    if not size or (int(size[1]), int(size[2])) != (expected['width'], expected['height']):
        raise ValueError('GPU desktop dimensions do not match requirements')
    parent = os.getppid()
    record = {'renderer': name, 'display': os.environ['DISPLAY'],
              'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              'session_pid': parent, 'session_start': process_start(parent)}
    temporary = ROOT / 'state' / f'gpu-ready-{os.getpid()}.json'
    try:
        temporary.write_text(json.dumps(record))
        temporary.replace(ROOT / 'state/gpu-ready.json')
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    if args.publish:
        publish()
    else:
        record = json.loads((ROOT / 'state/gpu-ready.json').read_text())
        verify_session(record, Path('/proc/sys/kernel/random/boot_id').read_text().strip())


if __name__ == '__main__':
    main()
