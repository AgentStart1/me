"""Build a pinned, opt-in Windows/WHPX runtime for Ubuntu OpenGL guests."""
import argparse
import ctypes
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request

from process_identity import identity, write_record
from whpx_runtime import ROOT, BuildInput, bundle, digest, extract, msys_root, verify as verify_whpx

CPU_ARGS = ['-accel', 'whpx', '-cpu', 'Westmere,-vmx,-svm']


@dataclass(frozen=True)
class Snapshot:
    lock: bytes
    inputs: tuple[BuildInput, ...]

    @classmethod
    def capture(cls):
        folder = ROOT / 'patches/viogpu-windows'
        lock = (folder / 'sources.json').read_bytes()
        sources = json.loads(lock)['sources']
        inputs = [BuildInput('build-virgl-whpx.sh', (ROOT / 'templates/build-virgl-whpx.sh').read_bytes())]
        for name, filename in [('qemu-whpx-reset', 'qemu-11.1.2-whpx-partition-reset.patch'),
                               ('qemu-whpx-cet', 'qemu-11.1.2-whpx-cet-xsave.patch'),
                               ('qemu-gl-snapshot', 'qemu-11.1.2-sdl-gl-snapshot.patch')]:
            inputs.append(BuildInput(name + '.patch', (ROOT / 'patches' / filename).read_bytes()))
        for name, output in [('qemu', 'qemu-virgl.patch'), ('virglrenderer', 'virglrenderer.patch')]:
            content = (folder / sources[name]['patch']).read_bytes()
            if hashlib.sha256(content).hexdigest() != sources[name]['patch_sha256']:
                raise ValueError('VirGL patch checksum mismatch')
            inputs.append(BuildInput(output, content))
        return cls(lock, tuple(inputs))

    @property
    def source_sha(self):
        return json.loads(self.lock)['sources']['qemu']['archive_sha256']

    def recipe(self):
        return hashlib.sha256(self.lock + b''.join(
            item.name.encode() + b'\0' + item.content for item in self.inputs)).hexdigest()


def location(cache=None, snapshot=None):
    snapshot = snapshot or Snapshot.capture()
    selected = cache or os.environ.get('QEMU_VIRGL_CACHE')
    parent = Path(selected) if selected else Path.home() / '.cache/me/virgl-whpx'
    return parent / snapshot.recipe()[:24]


def verify(runtime, snapshot=None):
    snapshot = snapshot or Snapshot.capture()
    manifest = json.loads((runtime / 'runtime.json').read_text())
    required = {'bin/libvirglrenderer-1.dll', 'bin/SDL2.dll', 'bin/libepoxy-0.dll',
                'recipe/qemu-gl-snapshot.patch',
                'share/qemu/vgabios-virtio.bin'}
    if not required.issubset(manifest.get('files', {})):
        raise ValueError('VirGL runtime dependencies are missing')
    executable = verify_whpx(runtime, snapshot)
    devices = subprocess.run([str(executable), '-device', 'help'], check=True,
                             capture_output=True, text=True, timeout=15)
    if '"virtio-vga-gl"' not in devices.stdout:
        raise ValueError('VirGL runtime has no virtio-vga-gl device')
    # Probe schema support without opening a window or starting a VM.
    options = subprocess.run([str(executable), '-display', 'sdl,hidden=on,gl=on', '-version'],
                             capture_output=True, text=True, timeout=15)
    if options.returncode:
        raise ValueError('VirGL runtime has no hidden SDL display option')
    return executable


def build(cache=None, msys2=None, qemu_archive=None, virgl_archive=None, jobs=8):
    if os.name != 'nt' or platform.machine().lower() not in {'amd64', 'x86_64'}:
        raise ValueError('VirGL/WHPX builds require Windows 11 x64')
    if sys.version_info < (3, 12):
        raise ValueError('VirGL/WHPX builds require Python 3.12 or later')
    if type(jobs) is not int or not 1 <= jobs <= 32:
        raise ValueError('Build jobs must be in 1..32')
    try:
        ctypes.WinDLL('WinHvPlatform.dll').WHvResetPartition
    except (OSError, AttributeError):
        raise ValueError('Windows 11 WHPX partition reset API is required') from None
    snapshot = Snapshot.capture()
    home = location(cache, snapshot)
    runtime = home / 'runtime'
    if runtime.exists():
        return verify(runtime, snapshot)
    if any(character.isspace() for character in str(home.resolve())):
        raise ValueError('Set QEMU_VIRGL_CACHE to a private path without spaces for the QEMU build')
    home.mkdir(parents=True, exist_ok=True)
    lock = home / 'build.lock'
    lock.mkdir()  # Never steal an active or interrupted build.
    try:
        write_record(lock / 'owner.json', {'pid': os.getpid(), 'identity': identity(os.getpid())})
        msys = msys_root(msys2)
        work = Path(tempfile.mkdtemp(prefix='build-', dir=home))
        sources = json.loads(snapshot.lock)['sources']
        for name, supplied in [('qemu', qemu_archive), ('virglrenderer', virgl_archive)]:
            entry = sources[name]
            archive = Path(supplied) if supplied else home / entry['url'].rsplit('/', 1)[1]
            if not archive.exists():
                print('Downloading pinned ' + name + ' source.', flush=True)
                with urllib.request.urlopen(entry['url'], timeout=60) as response, archive.open('xb') as output:
                    shutil.copyfileobj(response, output)
            private = work / archive.name
            shutil.copyfile(archive, private)
            if digest(private) != entry['archive_sha256']:
                raise ValueError(name + ' source checksum mismatch')
            extract(private, work)
        inputs = work / 'inputs'
        inputs.mkdir()
        for item in snapshot.inputs:
            (inputs / item.name).write_bytes(item.content)
        print('Building VirGL and WHPX-only QEMU; inspect ' + str(home / 'build.log'), flush=True)
        with (home / 'build.log').open('wb') as log:
            subprocess.run([str(msys / 'usr/bin/bash.exe'), str(inputs / 'build-virgl-whpx.sh'),
                            str(work), str(jobs)], check=True, stdout=log, stderr=subprocess.STDOUT)
        stage = work / 'runtime'
        qemu_source = work / 'qemu-11.1.2'
        bundle(work / 'qemu-build/qemu-system-x86_64.exe', qemu_source, stage, msys,
               dependency_dirs=(work / 'prefix/bin',))
        shutil.copytree(inputs, stage / 'recipe')
        (stage / 'recipe/sources.json').write_bytes(snapshot.lock)
        for name, source in [('qemu', qemu_source), ('virglrenderer', work / 'virglrenderer-1.3.0')]:
            target = stage / 'licenses' / name
            target.mkdir(parents=True)
            for file in source.iterdir():
                if file.is_file() and file.name.startswith(('LICENSE', 'COPYING')):
                    shutil.copy2(file, target / file.name)
        write_record(stage / 'runtime.json', {'recipe': snapshot.recipe(),
                     'sourceSha256': snapshot.source_sha,
                     'files': {p.relative_to(stage).as_posix(): digest(p)
                               for p in stage.rglob('*') if p.is_file()}})
        stage.rename(runtime)
        return verify(runtime, snapshot)
    except (KeyboardInterrupt, SystemExit):
        raise  # Keep ownership until native build children have been inspected.
    finally:
        if sys.exc_info()[0] not in (KeyboardInterrupt, SystemExit):
            (lock / 'owner.json').unlink(missing_ok=True)
            lock.rmdir()


def prepare(config, build_runtime=True):
    if config.get('os') != 'ubuntu' or not config.get('graphical') or config.get('qemu'):
        raise ValueError('virgl-whpx owns the executable and requires graphical Ubuntu')
    if config['qemu_args'] != CPU_ARGS or config.get('hardware_args'):
        raise ValueError('virgl-whpx requires the tested CPU arguments and standard hardware')
    executable = build() if build_runtime else location() / 'runtime/bin/qemu-system-x86_64.exe'
    return {**config, 'qemu': str(executable), 'qemu_args': [*CPU_ARGS,
            '-L', str(executable.parent.parent / 'share/qemu'), '-vga', 'none',
            '-device', 'virtio-vga-gl', '-display', 'sdl,gl=on,hidden=on']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', type=Path)
    parser.add_argument('--msys2-root', type=Path)
    parser.add_argument('--qemu-archive', type=Path)
    parser.add_argument('--virgl-archive', type=Path)
    parser.add_argument('--jobs', type=int, default=8)
    args = parser.parse_args()
    try:
        print(build(args.cache_dir, args.msys2_root, args.qemu_archive, args.virgl_archive, args.jobs))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        sys.exit(str(error))
