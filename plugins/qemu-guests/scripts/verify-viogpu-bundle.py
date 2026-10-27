"""Verify the experimental viogpu patch bundle without modifying source checkouts."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'patches/viogpu-windows'


def digest(content):
    return hashlib.sha256(content).hexdigest()


def relative_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
        raise ValueError('Invalid bundle path')
    return path


def verify(bundle=BUNDLE, sources=None):
    lock = json.loads((bundle / 'sources.json').read_bytes())
    if lock['schema'] != 1 or set(lock['sources']) != {'qemu', 'virglrenderer', 'mesa'}:
        raise ValueError('Unexpected source lock')
    captured = []
    for name, source in lock['sources'].items():
        patch_path = relative_name(source['patch'])
        patch = (bundle / patch_path).read_bytes()
        if digest(patch) != source['patch_sha256']:
            raise ValueError(name + ': patch checksum mismatch')
        originals = {}
        for filename, hashes in source['files'].items():
            relative_name(filename)
            if sources and name in sources:
                content = (sources[name] / filename).read_bytes()
                if digest(content) != hashes['before']:
                    raise ValueError(name + ': source mismatch: ' + filename)
                originals[filename] = content
        captured.append((name, source, patch, originals))
    # All selected inputs are captured and verified before any patch process runs.
    for name, source, patch, originals in captured:
        if not originals:
            continue
        with tempfile.TemporaryDirectory(prefix='viogpu-check-') as directory:
            temporary = Path(directory)
            for filename, content in originals.items():
                target = temporary / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            subprocess.run(['git', 'init', '-q', str(temporary)], check=True)
            subprocess.run(['git', '-c', 'core.autocrlf=false', 'apply', '--check', '-'],
                           input=patch, cwd=temporary, check=True, capture_output=True)
            subprocess.run(['git', '-c', 'core.autocrlf=false', 'apply', '-'],
                           input=patch, cwd=temporary, check=True, capture_output=True)
            for filename, hashes in source['files'].items():
                if digest((temporary / filename).read_bytes()) != hashes['after']:
                    raise ValueError(name + ': patched source mismatch: ' + filename)
    return {'integrity': 'PASS', 'source_application': sorted(sources or {})}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for source in ('qemu', 'virglrenderer', 'mesa'):
        parser.add_argument('--' + source + '-source', type=Path)
    args = parser.parse_args()
    selected = {name: getattr(args, name + '_source') for name in
                ('qemu', 'virglrenderer', 'mesa') if getattr(args, name + '_source')}
    print(json.dumps(verify(sources=selected)))
