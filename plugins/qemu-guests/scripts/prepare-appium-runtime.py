#!/usr/bin/env python3
"""Overlay prepared local extensions onto an offline runtime without guest npm/build hooks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile


def prepare(base, output, extensions, windows_desktop=False, assets=None, requirements=None, platform=None):
    if output.exists():
        raise ValueError('Choose a new runtime output; existing archives are preserved')
    node = shutil.which('node')
    if not node:
        raise ValueError('Host Node is required for runtime metadata preparation')
    templates = Path(__file__).resolve().parents[1] / 'templates/guests'
    required = None
    if requirements:
        from test_requirements import load, verify_runtime_target
        from project_setup_hooks import prepare_host
        required = load(requirements, platform)
        verify_runtime_target(base, platform)
        prepare_host(required['hooks']['host_prepare'], output.parent / (output.stem + '-logs'))
    with tempfile.TemporaryDirectory(prefix='prepared-appium-') as folder:
        root = Path(folder) / 'runtime'; root.mkdir()
        with zipfile.ZipFile(base) as archive:
            for name in archive.namelist():
                if not (root / name).resolve().is_relative_to(root.resolve()):
                    raise ValueError('Runtime archive contains an escaping path')
            archive.extractall(root)
        manifest = json.loads((root / 'runtime.json').read_text())
        if assets:
            data = json.loads(Path(assets).read_text(encoding='utf-8-sig'))
            if not isinstance(data, dict) or set(data) - {'classpath'} != {'files', 'environment'}:
                raise ValueError('Runtime assets require files and environment')
            for item in data['files']:
                source = Path(item['source']).resolve()
                target = (root / 'assets' / item['destination']).resolve()
                if not target.is_relative_to(root / 'assets') or target == root / 'assets':
                    raise ValueError('Runtime assets must stay below the assets directory')
                if source.is_dir():
                    shutil.copytree(source, target, ignore=shutil.ignore_patterns('.git', '.ssh', 'secrets', '*.pem', '*.key'))
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
            if not isinstance(data['environment'], dict) or any(not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', k) or not isinstance(v, str) or '\0' in v for k,v in data['environment'].items()):
                raise ValueError('Runtime environment requires valid string variables')
            manifest['environment'] = data['environment']
            manifest['classpath'] = data.get('classpath', {})
            for coordinate, relative in manifest['classpath'].items():
                target = (root / relative).resolve()
                if not target.is_relative_to(root / 'assets') or not target.is_file():
                    raise ValueError('Prebuilt classpath dependencies must name an existing runtime asset')
            (root / 'runtime.json').write_text(json.dumps(manifest))
        prepared = []
        for directory in extensions:
            package = json.loads((directory / 'package.json').read_text())
            metadata = package.get('appium', {})
            name = metadata.get('pluginName') or metadata.get('driverName')
            if not isinstance(name, str) or not re.fullmatch('[a-z][a-z0-9-]*', name):
                raise ValueError('Prepared extension needs a valid Appium driverName/pluginName')
            target = root / 'local-extensions' / name
            shutil.copytree(directory, target, ignore=shutil.ignore_patterns('.git', '.ssh', 'secrets', '*.pem', '*.key'))
            prepared.append({'path': target.as_posix(), 'package': package})
        metadata = Path(folder) / 'extensions.json'
        metadata.write_text(json.dumps(prepared))
        script = Path(folder) / 'prepare-runtime.cjs'
        script.write_bytes((templates / 'prepare-runtime.cjs.tpl').read_bytes())
        subprocess.run([node, str(script), root.as_posix(), str(metadata)], check=True)
        if windows_desktop:
            if os.name != 'nt' or manifest['platform'] != 'win32':
                raise ValueError('Build the Windows desktop helper on a Windows host')
            source = Path(folder) / 'desktop-helper.cs'
            source.write_bytes((templates / 'desktop-helper.cs.tpl').read_bytes())
            compiler = Path(folder) / 'compile-desktop-helper.ps1'
            compiler.write_bytes((templates / 'compile-desktop-helper.ps1.tpl').read_bytes())
            # Compilation happens here on the host. Guests only load the assembly.
            subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(compiler),
                str(source), str(root / 'desktop-helper.dll')], check=True)
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob('*')):
                if path.is_file():
                    archive.write(path, path.relative_to(root).as_posix())
    with output.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if required:
        from test_requirements import verify_runtime
        verify_runtime(output, required, platform)
    return {'runtime_archive': str(output), 'sha256': digest}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--extension', action='append', default=[], type=Path,
                        help='Host-prepared extension directory including any prebuilt native dependencies')
    parser.add_argument('--windows-desktop', action='store_true')
    parser.add_argument('--assets', type=Path, help='Operator-owned prebuilt files and service environment manifest')
    parser.add_argument('--requirements', type=Path)
    parser.add_argument('--platform', choices=['windows', 'ubuntu'])
    args = parser.parse_args()
    print(json.dumps(prepare(args.base.resolve(), args.output.resolve(),
                             [p.resolve() for p in args.extension], args.windows_desktop, args.assets, args.requirements, args.platform)))
