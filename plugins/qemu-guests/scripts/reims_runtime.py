"""Build a self-contained, pinned Windows/WHPX macOS GPU runtime."""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile

from process_identity import identity, write_record
from reims_sources import ROOT, Snapshot, checkout
from whpx_runtime import bundle, digest, msys_root, verify as verify_whpx

CPU_ARGS = ['-accel', 'whpx,hyperv=off,kernel-irqchip=off', '-cpu',
            'Skylake-Client,-hle,-rtm,vendor=GenuineIntel,-vmx,-svm,-hypervisor,+invtsc,vmware-cpuid-freq=on']


def location(cache=None, snapshot=None):
    snapshot = snapshot or Snapshot.capture()
    selected = cache or os.environ.get('QEMU_REIMS_CACHE')
    parent = Path(selected) if selected else Path.home() / '.cache/me/reims-whpx'
    return parent / snapshot.recipe()[:24]


def verify(runtime, snapshot=None):
    snapshot = snapshot or Snapshot.capture()
    manifest = json.loads((runtime / 'runtime.json').read_text())
    if 'share/qemu/ReimsVgpu.rom' not in manifest.get('files', {}):
        raise ValueError('GPU runtime option ROM is missing')
    executable = verify_whpx(runtime, snapshot)
    result = subprocess.run([str(executable), '-device', 'help'], capture_output=True,
                            text=True, check=True, timeout=30)
    if 'apple-gfx-pci' not in result.stdout:
        raise ValueError('GPU runtime has no apple-gfx-pci device')
    return executable


def run_build(script, workspace, msys, jobs, log):
    result = subprocess.run([str(msys / 'usr/bin/bash.exe'), str(script),
                             str(workspace), str(jobs)], stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError('GPU runtime build failed; inspect build.log')


def pkgconfig(snapshot, workspace):
    lines = (workspace / 'native-static-libs.log').read_text(errors='replace').splitlines()
    matches = [line.split('native-static-libs:', 1)[1].strip() for line in lines
               if 'note: native-static-libs:' in line]
    if len(matches) != 1 or not re.fullmatch(r'(?:-l[A-Za-z0-9_+.-]+\s*)+', matches[0]):
        raise ValueError('Rust native link dependencies are missing or invalid')
    source = workspace / 'reims-vgpu'
    values = {'LIBRARY': (workspace / 'target/release/libreims_vgpu_c.a').as_posix(),
              'NATIVE_LIBS': matches[0], 'INCLUDE': (source / 'crates/reims-vgpu-c/include').as_posix(),
              'ROM': (source / 'firmware/build/ReimsVgpu.rom').as_posix()}
    text = next(item.content.decode() for item in snapshot.templates if item.name == 'reims-vgpu.pc.tpl')
    for name, value in values.items():
        text = text.replace('{{' + name + '}}', value)
    destination = workspace / 'package/lib/pkgconfig'
    destination.mkdir(parents=True)
    (destination / 'reims-vgpu.pc').write_text(text, newline='\n')


def build(cache=None, msys2=None, jobs=6):
    if os.name != 'nt' or platform.machine().lower() not in {'amd64', 'x86_64'}:
        raise ValueError('The GPU runtime requires Windows 11 x64 and WHPX')
    if sys.getwindowsversion().build < 22000:
        raise ValueError('The GPU runtime requires Windows 11 or later')
    if type(jobs) is not int or jobs < 1:
        raise ValueError('Build jobs must be a positive integer')
    snapshot = Snapshot.capture()
    home = location(cache, snapshot)
    runtime = home / 'runtime'
    if runtime.exists():
        return verify(runtime, snapshot)
    if any(character.isspace() for character in str(home.resolve())):
        raise ValueError('QEMU cannot build in paths with spaces; set QEMU_REIMS_CACHE to a private path without spaces')
    home.mkdir(parents=True, exist_ok=True)
    lock = home / 'build.lock'
    lock.mkdir()  # A busy/interrupted build is never adopted or removed.
    record = {'pid': os.getpid(), 'identity': identity(os.getpid())}
    write_record(lock / 'owner.json', record)
    try:
        msys = msys_root(msys2)
        workspace = Path(tempfile.mkdtemp(prefix='build-', dir=home))
        inputs = workspace / 'inputs'
        snapshot.write(inputs)
        with (home / 'build.log').open('wb') as log:
            sources = checkout(snapshot, workspace, log)
            print('Building Windows Vulkan library and option ROM.', flush=True)
            run_build(inputs / 'build-reims-library.sh', workspace, msys, jobs, log)
            pkgconfig(snapshot, workspace)
            print('Building WHPX-only QEMU with the patched GPU library.', flush=True)
            run_build(inputs / 'build-reims-qemu.sh', workspace, msys, jobs, log)
        stage = workspace / 'runtime'
        bundle(workspace / 'qemu-build/qemu-system-x86_64.exe', sources['qemu'], stage, msys)
        shutil.copy2(sources['reims-vgpu'] / 'firmware/build/ReimsVgpu.rom', stage / 'share/qemu')
        shutil.copytree(inputs, stage / 'recipe')
        # Keep the upstream terms with the combined executable and its recipe.
        for name, source in sources.items():
            target = stage / 'licenses' / name
            target.mkdir(parents=True)
            for path in source.iterdir():
                if path.is_file() and path.name.startswith(('LICENSE', 'COPYING')):
                    shutil.copy2(path, target / path.name)
                elif path.is_dir() and path.name == 'LICENSES':
                    shutil.copytree(path, target / path.name)
        manifest = {'recipe': snapshot.recipe(), 'sourceSha256': snapshot.source_sha,
                    'sources': json.loads(snapshot.lock)['sources'],
                    'files': {path.relative_to(stage).as_posix(): digest(path)
                              for path in stage.rglob('*') if path.is_file()}}
        write_record(stage / 'runtime.json', manifest)
        # Verify the published path; Windows image handles can prevent renaming
        # a directory after running its PE executable.
        stage.rename(runtime)
        executable = verify(runtime, snapshot)
        print('Verified Windows/WHPX GPU runtime is ready.', flush=True)
        return executable
    except (KeyboardInterrupt, SystemExit):
        raise  # Retain build ownership until child exit has been inspected.
    finally:
        if sys.exc_info()[0] not in (KeyboardInterrupt, SystemExit):
            (lock / 'owner.json').unlink(missing_ok=True)
            lock.rmdir()


def prepare(config, build_runtime=True):
    if config['os'] != 'macos' or config.get('qemu'):
        raise ValueError('reims-whpx owns the QEMU executable and requires a macOS profile')
    if config['qemu_args'] != CPU_ARGS:
        raise ValueError('reims-whpx requires the tested WHPX/CPU arguments')
    if config.get('install_reboots'):
        raise ValueError('reims-whpx uses warm installation reboots')
    executable = build() if build_runtime else location() / 'runtime/bin/qemu-system-x86_64.exe'
    data = executable.parent.parent / 'share/qemu'
    hardware = [value.replace('{reims_rom}', (data / 'ReimsVgpu.rom').as_posix())
                for value in config['hardware_args']]
    return {**config, 'qemu': str(executable), 'hardware_args': hardware,
            'qemu_args': [*config['qemu_args'], '-L', str(data)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', type=Path)
    parser.add_argument('--msys2-root', type=Path)
    parser.add_argument('--jobs', type=int, default=6)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    executable = verify(location(args.cache_dir) / 'runtime') if args.verify_only else build(
        args.cache_dir, args.msys2_root, args.jobs)
    print(executable)


if __name__ == '__main__':
    main()
