#!/usr/bin/env python3
"""Deterministic device fixtures; only implements the panels' read operations."""
import base64
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
with open(os.environ['FAKE_ADB_LOG'], 'a', encoding='utf-8') as stream:
    stream.write(json.dumps(args) + '\n')
config = json.loads(Path(os.environ['FAKE_ADB_CONFIG']).read_text())
if config.get('fail'):
    raise SystemExit(1)
if args == ['devices', '-l']:
    print('List of devices attached')
    for device in config['devices']:
        print(device['serial'], device.get('connection','device'), 'model:Test_Device')
    raise SystemExit(0)
if len(args) < 3 or args[0] != '-s':
    raise SystemExit(2)
device = next(item for item in config['devices'] if item['serial'] == args[1])
command = args[2:]
if command == ['emu','avd','name']:
    print(device.get('avd',''))
    print('OK')
elif command == ['exec-out','screencap','-p']:
    sys.stdout.buffer.write(base64.b64decode(device['png']))
elif command[0] == 'shell' and command[1].startswith('getprop '):
    print('\n'.join([device.get('boot','1'),device.get('avd',''), '15', '35',device.get('qemu','1')]))
elif command[0] == 'shell' and command[1].startswith('if [ -d '):
    print(device.get('lock','absent\n'), end='')
else:
    raise SystemExit('Unexpected or mutating ADB command')
