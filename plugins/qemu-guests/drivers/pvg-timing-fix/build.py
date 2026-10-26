#!/usr/bin/env python3
"""Rebuild on a designated preparation machine; never connect to a work VM."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--lilu-source', type=Path, required=True)
parser.add_argument('--kernel-sdk', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--clang', default='clang++')
parser.add_argument('--link', action='store_true', help='Link with Xcode on this macOS preparation machine')
args = parser.parse_args()
manifest = json.loads((root / 'artifact.json').read_text())
for source, revision in ((args.lilu_source, manifest['lilu_source']),
                         (args.kernel_sdk, manifest['kernel_sdk_source'])):
    actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD']).decode().strip()
    if actual != revision or subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain']):
        raise ValueError('Use the clean pinned dependency source revision from artifact.json')
if args.link and sys.platform != 'darwin':
    raise ValueError('Final kext linking requires Xcode on a designated macOS preparation machine')
args.output.mkdir(parents=True, exist_ok=False)
flags = ['-target', 'x86_64-apple-macosx10.6.0', '-mkernel', '-nostdlib', '-nostdinc++',
         '-fno-builtin', '-fno-stack-protector', '-mno-red-zone', '-Os', '-fno-sanitize=all',
         '-Wall', '-Wextra', '-std=c++17', '-fapple-kext', '-fno-rtti', '-fno-exceptions',
         '-fno-use-cxa-atexit', '-fno-register-global-dtors-with-atexit', '-fno-pic',
         '-DKERNEL', '-DKERNEL_PRIVATE', '-DLILU_KEXTPATCH_SUPPORT', '-Wno-unused-parameter',
         '-Wno-builtin-macro-redefined', '-D__DATE__="Oct 25 2026"',
         '-DPRODUCT_NAME=PvgTimingFix', '-DMODULE_VERSION=0.1.0',
         '-isystem', str(args.lilu_source / 'Lilu'), '-isystem', str(args.kernel_sdk / 'Headers')]
for path, name in ((root, 'pvg-timing-fix'), (args.lilu_source, 'lilu'), (args.kernel_sdk, 'kernel-sdk')):
    flags.append('-ffile-prefix-map=' + str(path.resolve()) + '=/src/' + name)
subprocess.run([args.clang, *flags, '-c', str(root / 'PvgTimingFix.cpp'),
                '-o', str(args.output / 'PvgTimingFix.o')], check=True)
intermediate = args.output / 'plugin_start.ll'
subprocess.run([args.clang, *flags, '-S', '-emit-llvm',
                str(args.lilu_source / 'Lilu/Library/plugin_start.cpp'), '-o', str(intermediate)], check=True)
ir = intermediate.read_text()
declarations = [line for line in ir.splitlines() if line.startswith('@llvm.global_dtors =')]
if len(declarations) != 1 or '@llvm.compiler.used =' in ir:
    raise ValueError('Unreviewed LLVM destructor layout; inspect retained IR')
destructors = re.findall(r'ptr (@[A-Za-z0-9_.$]+)', declarations[0])
if len(destructors) != 1:
    raise ValueError('Unreviewed LLVM destructor count')
# LLVM's user-mode Darwin lowering uses __cxa_atexit. XNU requires the pointer section.
replacement = ('@pvg_kernel_dtors = internal global [1 x ptr] [ptr ' + destructors[0] +
               '], section "__DATA,__mod_term_func,mod_term_funcs", align 8\n'
               '@llvm.compiler.used = appending global [1 x ptr] [ptr @pvg_kernel_dtors], section "llvm.metadata"')
rewritten = args.output / 'plugin_start-kernel.ll'
rewritten.write_text(ir.replace(declarations[0], replacement), newline='\n')
subprocess.run([args.clang, '-target', 'x86_64-apple-macosx10.6.0', '-fno-pic', '-c', str(rewritten),
                '-o', str(args.output / 'plugin_start.o')], check=True)
if args.link:
    subprocess.run(['xcrun', 'ld', '-arch', 'x86_64', '-kext', '-undefined', 'dynamic_lookup',
                    '-o', str(args.output / 'PvgTimingFix'), str(args.output / 'PvgTimingFix.o'),
                    str(args.output / 'plugin_start.o')], check=True)
print('Objects prepared. Final linking uses Xcode on the designated macOS preparation machine.')
