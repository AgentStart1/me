#!/usr/bin/env python3
"""Export the private payload for building a macOS first-boot product package."""
import argparse
import os
from pathlib import Path
from guest_config import load
from guest_seed import payload_archive

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('profile', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
config = load(args.profile)
if config['os'] != 'macos':
    parser.error('A macOS profile is required')
descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, 'wb') as output:
    output.write(payload_archive(config))
print('Private macOS bootstrap payload exported; build it with build-macos-bootstrap.sh on macOS.')
