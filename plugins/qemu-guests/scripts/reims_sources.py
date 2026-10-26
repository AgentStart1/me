"""Capture and apply the plugin-owned Windows GPU dependency patch set."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Input:
    name: str
    content: bytes


@dataclass(frozen=True)
class Snapshot:
    lock: bytes
    patches: tuple[Input, ...]
    templates: tuple[Input, ...]

    @property
    def source_sha(self):
        return hashlib.sha256(self.lock).hexdigest()

    @classmethod
    def capture(cls):
        directory = ROOT / 'patches/reims-windows'
        lock = (directory / 'sources.json').read_bytes()
        sources = json.loads(lock)['sources']
        if set(sources) != {'reims-vgpu', 'metal2vulkan', 'qemu'}:
            raise ValueError('Incomplete GPU source lock')
        patches = []
        for source in sources.values():
            name = source['patch']
            if Path(name).name != name:
                raise ValueError('Invalid dependency patch name')
            content = (directory / name).read_bytes()
            if hashlib.sha256(content).hexdigest() != source['sha256']:
                raise ValueError('GPU dependency patch checksum mismatch')
            patches.append(Input(name, content))
        templates = tuple(Input(name, (ROOT / 'templates' / name).read_bytes()) for name in
                          ('build-reims-library.sh', 'build-reims-qemu.sh', 'reims-vgpu.pc.tpl'))
        return cls(lock, tuple(patches), templates)

    def recipe(self):
        digest = hashlib.sha256(self.lock)
        for item in (*self.patches, *self.templates):
            digest.update(item.name.encode() + b'\0' + item.content)
        return digest.hexdigest()

    def write(self, directory):
        directory.mkdir()
        (directory / 'sources.json').write_bytes(self.lock)
        for item in (*self.patches, *self.templates):
            (directory / item.name).write_bytes(item.content)


def checkout(snapshot, workspace, log):
    """Fresh public checkouts only; never patch an operator's existing source tree."""
    sources = json.loads(snapshot.lock)['sources']
    directories = {'metal2vulkan': workspace / 'metal2vulkan-windows',
                   'reims-vgpu': workspace / 'reims-vgpu',
                   'qemu': workspace / 'reims-vgpu/vendor/qemu'}
    patches = {item.name: item.content for item in snapshot.patches}
    for name in ('metal2vulkan', 'reims-vgpu', 'qemu'):
        source, destination = sources[name], directories[name]
        destination.mkdir(parents=True, exist_ok=True)
        if any(destination.iterdir()):
            raise ValueError('Source destination must be empty')

        def git(*args, data=None):
            result = subprocess.run(['git', '-C', str(destination), *args], input=data,
                                    stdout=log, stderr=subprocess.STDOUT)
            if result.returncode:
                raise RuntimeError('GPU source preparation failed; inspect build.log')

        print('Preparing pinned GPU dependency: ' + name, flush=True)
        git('init', '-q')
        git('config', 'core.autocrlf', 'false')
        git('config', 'core.longpaths', 'true')
        git('remote', 'add', 'origin', source['url'])
        git('fetch', '--depth=1', 'origin', source['revision'])
        git('checkout', '--detach', 'FETCH_HEAD')
        patch = patches[source['patch']]
        git('apply', '--check', '-', data=patch)
        git('apply', '-', data=patch)
        if source.get('patched_tree'):
            git('add', '--all')
            actual = subprocess.check_output(['git', '-C', str(destination), 'write-tree']).decode().strip()
            if actual != source['patched_tree']:
                raise ValueError('Patched dependency tree does not match the qualified source')
    return directories
