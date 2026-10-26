#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyfatfs==1.1.0", "setuptools<81"]
# ///
"""Install the bundled, qualified timing fix into a new operator-supplied EFI image."""
import argparse
from pathlib import Path
from macos_gpu_boot import prepare

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--opencore', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--guest-build', required=True)
parser.add_argument('--lilu-archive', type=Path)
parser.add_argument('--fat-offset', type=int, default=1048576)
args = parser.parse_args()
prepare(args.opencore, args.output, args.guest_build, args.lilu_archive, args.fat_offset)
print('Independent GPU boot image prepared; original firmware preserved.')
