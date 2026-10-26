"""Build and verify a private QEMU runtime; never replace the system executable."""
import argparse
import bz2
import ctypes
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VERSION = '11.1.2'
SOURCE_SHA = '731b5681e4bb18be313231579b8efd0296c5b015fa36dc533874b639ba838016'
SOURCE_URL = f'https://download.qemu.org/qemu-{VERSION}.tar.xz'
PATCH = ROOT / f'patches/qemu-{VERSION}-whpx-partition-reset.patch'
PATCHES = (PATCH, ROOT / f'patches/qemu-{VERSION}-whpx-cet-xsave.patch')


def digest(path):
    with Path(path).open('rb') as stream:
        result = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
        return result.hexdigest()


@dataclass(frozen=True)
class BuildInput:
    name: str
    content: bytes


@dataclass(frozen=True)
class BuildSnapshot:
    version: str
    source_url: str
    source_sha: str
    template: BuildInput
    patches: tuple[BuildInput, ...]

    @classmethod
    def capture(cls):
        template = ROOT / 'templates/build-whpx-qemu.sh'
        return cls(VERSION, SOURCE_URL, SOURCE_SHA,
                   BuildInput(template.name, template.read_bytes()),
                   tuple(BuildInput(path.name, path.read_bytes()) for path in PATCHES))

    def recipe(self):
        # Preserve cache identities for unchanged, previously verified inputs.
        patches = b''.join(item.name.encode() + b'\0' + item.content for item in self.patches)
        return hashlib.sha256(patches + self.template.content).hexdigest()


def recipe(snapshot=None):
    return (snapshot or BuildSnapshot.capture()).recipe()


def location(cache=None, snapshot=None):
    snapshot = snapshot or BuildSnapshot.capture()
    parent = Path(cache) if cache else Path.home() / '.cache/me/qemu-whpx'
    return parent / (snapshot.version + '-' + snapshot.recipe()[:16])


def verify_files(runtime, snapshot=None):
    snapshot = snapshot or BuildSnapshot.capture()
    manifest = json.loads((runtime / 'runtime.json').read_text())
    if not isinstance(manifest, dict) or manifest.get('recipe') != snapshot.recipe() or manifest.get('sourceSha256') != snapshot.source_sha:
        raise ValueError('WHPX runtime recipe does not match this plugin')
    files = manifest.get('files')
    if not isinstance(files, dict) or any(not isinstance(name, str) or not isinstance(value, str)
                                         or not re.fullmatch('[a-f0-9]{64}', value) for name, value in files.items()):
        raise ValueError('WHPX runtime manifest is invalid')
    required = {'bin/qemu-system-x86_64.exe', 'share/qemu/bios-256k.bin', 'share/qemu/vgabios-stdvga.bin'}
    if not required.issubset(files):
        raise ValueError('WHPX runtime manifest is incomplete')
    for relative, expected in files.items():
        path = (runtime / relative).resolve()
        if not path.is_relative_to(runtime.resolve()) or digest(path) != expected:
            raise ValueError('WHPX runtime file verification failed')
    return runtime / 'bin/qemu-system-x86_64.exe'


def verify(runtime, snapshot=None):
    executable = verify_files(runtime, snapshot)
    result = subprocess.run([str(executable), '-accel', 'help'], check=True,
                            capture_output=True, text=True, timeout=15)
    if result.stdout.splitlines()[1:] != ['whpx']:
        raise ValueError('Managed runtime must support WHPX only')
    return executable


def msys_root(explicit=None):
    candidates = [explicit or os.environ.get('QEMU_MSYS2_ROOT'), str(Path.home() / 'msys2'), 'C:/msys64']
    for candidate in candidates:
        if candidate and (Path(candidate) / 'usr/bin/bash.exe').is_file():
            return Path(candidate).resolve()
    raise ValueError('Install MSYS2 UCRT64 or set QEMU_MSYS2_ROOT; no accelerator fallback')


def extract(archive, destination):
    with tarfile.open(archive) as source:
        # Firmware source/CI symlinks are irrelevant to this Windows-only build.
        members = [member for member in source.getmembers()
                   if not member.issym() and not member.islnk()
                   and '/roms/' not in member.name and '/tests/lcitool/' not in member.name]
        source.extractall(destination, members=members, filter='data')


def bundle(executable, source, stage, msys):
    binaries = stage / 'bin'
    binaries.mkdir(parents=True)
    pending = [executable]
    copied = set()
    while pending:
        path = pending.pop()
        if path.name.lower() in copied:
            continue
        shutil.copy2(path, binaries / path.name)
        copied.add(path.name.lower())
        result = subprocess.run([str(msys / 'ucrt64/bin/objdump.exe'), '-p', str(path)],
                                check=True, capture_output=True, text=True, timeout=30)
        for name in re.findall(r'DLL Name:\s*(\S+)', result.stdout):
            dependency = msys / 'ucrt64/bin' / name
            if dependency.is_file():
                pending.append(dependency)
            elif not (Path(os.environ['SystemRoot']) / 'System32' / name).is_file() and not name.lower().startswith(('api-ms-', 'ext-ms-')):
                raise ValueError('Missing runtime DLL: ' + name)
    firmware = stage / 'share/qemu'
    firmware.mkdir(parents=True)
    for path in (source / 'pc-bios').iterdir():
        if path.is_file() and path.suffix in {'.bin', '.rom', '.fd', '.txt'}:
            shutil.copy2(path, firmware / path.name)
        elif path.name.endswith('.fd.bz2'):
            (firmware / path.stem).write_bytes(bz2.decompress(path.read_bytes()))


def build(cache=None, msys2=None, archive=None, jobs=8):
    if os.name != 'nt' or platform.machine().lower() not in {'amd64', 'x86_64'}:
        raise ValueError('Managed WHPX builds require Windows 11 x64')
    if sys.version_info < (3, 12):
        raise ValueError('Managed WHPX builds require Python 3.12 or later')
    try:
        ctypes.WinDLL('WinHvPlatform.dll').WHvResetPartition
    except (OSError, AttributeError):
        raise ValueError('Windows WHPX partition reset API unavailable; Windows 11 is required') from None
    snapshot = BuildSnapshot.capture()
    home = location(cache, snapshot)
    runtime = home / 'runtime'
    if runtime.exists():
        return verify(runtime, snapshot)
    home.mkdir(parents=True, exist_ok=True)
    lock = home / 'build.lock'
    try:
        lock.mkdir()
    except FileExistsError:
        raise RuntimeError('WHPX build is busy or interrupted; inspect build.lock and build.log') from None
    try:
        (lock / 'owner.json').write_text(json.dumps({'pid': os.getpid()}))
        msys = msys_root(msys2)
        archive = Path(archive) if archive else home / f'qemu-{snapshot.version}.tar.xz'
        if not archive.exists():
            print('Downloading pinned QEMU source.', flush=True)
            with urllib.request.urlopen(snapshot.source_url, timeout=60) as response, archive.open('xb') as output:
                shutil.copyfileobj(response, output)
        # A unique workspace preserves failed builds without reusing partial output.
        work = Path(tempfile.mkdtemp(prefix='build-', dir=home))
        # Verify and extract the same private copy; the operator's archive can change.
        private_archive = work / f'qemu-{snapshot.version}.tar.xz'
        shutil.copyfile(archive, private_archive)
        if digest(private_archive) != snapshot.source_sha:
            raise ValueError('QEMU source checksum mismatch; archive retained for inspection')
        inputs = work / 'inputs'
        inputs.mkdir()
        for item in (snapshot.template, *snapshot.patches):
            (inputs / item.name).write_bytes(item.content)
        print('Extracting verified QEMU source.', flush=True)
        extract(private_archive, work)
        source = work / f'qemu-{snapshot.version}'
        output = work / 'output'
        print('Building WHPX-only QEMU; details: ' + str(home / 'build.log'), flush=True)
        with (home / 'build.log').open('wb') as log:
            # Console cancellation reaches the build's children too. Keep the lock
            # after cancellation until their termination has been inspected.
            result = subprocess.run([str(msys / 'usr/bin/bash.exe'),
                                     str(inputs / snapshot.template.name),
                                     str(source), str(output), str(jobs),
                                     *(str(inputs / item.name) for item in snapshot.patches)],
                                    stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError('WHPX build failed; inspect ' + str(home / 'build.log'))
        stage = work / 'runtime'
        bundle(output / 'qemu-system-x86_64.exe', source, stage, msys)
        for item in (snapshot.template, *snapshot.patches):
            (stage / item.name).write_bytes(item.content)
        for name in ('COPYING', 'LICENSE'):
            if (source / name).is_file():
                shutil.copy2(source / name, stage / name)
        manifest = {'version': snapshot.version, 'sourceUrl': snapshot.source_url,
                    'sourceSha256': snapshot.source_sha, 'recipe': snapshot.recipe(),
                    'files': {str(p.relative_to(stage)).replace('\\', '/'): digest(p)
                              for p in stage.rglob('*') if p.is_file()}}
        (stage / 'runtime.json').write_text(json.dumps(manifest, indent=2))
        # Executing a staged PE can leave Windows image/AV handles that deny
        # directory rename. Publish the complete hash-checked tree first; every
        # caller must still pass the final-path accelerator probe before use.
        verify_files(stage, snapshot)
        stage.rename(runtime)
        executable = verify(runtime, snapshot)
        print('Verified WHPX-only runtime is ready.', flush=True)
        return executable
    except (KeyboardInterrupt, SystemExit):
        raise  # Retain build ownership; children may still be shutting down.
    finally:
        # Only definitive completion releases this build's reservation.
        if sys.exc_info()[0] not in (KeyboardInterrupt, SystemExit):
            (lock / 'owner.json').unlink(missing_ok=True)
            lock.rmdir()


def prepare(config, build_runtime=True):
    if config.get('qemu_runtime') == 'reims-whpx':
        from reims_runtime import prepare as prepare_gpu
        return prepare_gpu(config, build_runtime)
    if config.get('qemu_runtime', 'system') != 'whpx-reset':
        return config
    if config.get('qemu'):
        raise ValueError('qemu_runtime=whpx-reset owns the executable; remove qemu override')
    args = config['qemu_args']
    if args != ['-accel', 'whpx', '-cpu', 'Westmere,-vmx,-svm']:
        raise ValueError('Managed WHPX runtime requires the tested accelerator/CPU arguments')
    executable = build() if build_runtime else location() / 'runtime/bin/qemu-system-x86_64.exe'
    runtime = executable.parent.parent
    return {**config, 'qemu': str(executable),
            'qemu_args': [*args, '-L', str(runtime / 'share/qemu')]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', type=Path)
    parser.add_argument('--msys2-root', type=Path)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--jobs', type=int, default=8, choices=range(1, 33))
    args = parser.parse_args()
    print(build(args.cache_dir, args.msys2_root, args.archive, args.jobs))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        sys.exit(str(error))
