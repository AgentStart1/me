#!/usr/bin/env python3
"""Build an offline Appium runtime for a guest matching the preparation OS/CPU."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys
import zipfile


def build(output, drivers, plugins):
    node = shutil.which('node')
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    if not node or not npm:
        raise ValueError('Install a Node version supported by Appium 3 and npm >=10')
    if output.exists():
        raise ValueError('Output already exists; choose a new archive path')
    with tempfile.TemporaryDirectory(prefix='appium-runtime-') as temporary:
        root = Path(temporary)
        runtime = root / 'runtime'
        runtime.mkdir()
        shutil.copy2(node, runtime / ('node.exe' if os.name == 'nt' else 'node'))
        # The builder never starts a server or touches the preparation desktop.
        subprocess.run([npm, 'install', '--prefix', str(runtime), '--no-audit', '--no-fund',
                        'appium@3.2.2'], check=True, shell=False)
        environment = {**os.environ, 'APPIUM_HOME': str(runtime / 'extensions')}
        cli = [node, str(runtime / 'node_modules/appium/index.js')]
        for driver in drivers:
            subprocess.run([*cli, 'driver', 'install', '--source=npm', driver], env=environment, check=True)
        for plugin in plugins:
            subprocess.run([*cli, 'plugin', 'install', '--source=npm', plugin], env=environment, check=True)
        names = subprocess.check_output([node, '-e',
            "const fs=require('fs'),p=require('path'),r=process.argv[1],y=require(p.join(r,'node_modules/yaml'));"
            "const f=p.join(r,'extensions/node_modules/.cache/appium/extensions.yaml');"
            "console.log(JSON.stringify(fs.existsSync(f)?Object.keys(y.parse(fs.readFileSync(f,'utf8')).plugins||{}):[]))",
            str(runtime)], text=True)
        manifest = {'platform': sys.platform, 'source_root': str(runtime), 'drivers': drivers,
                    'plugins': json.loads(names),
                    'arch': subprocess.check_output([node, '-p', 'process.arch'], text=True).strip(),
                    'node': subprocess.check_output([node, '--version'], text=True).strip(), 'appium': '3.2.2'}
        (runtime / 'runtime.json').write_text(json.dumps(manifest), encoding='utf-8')
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in runtime.rglob('*'):
                if path.is_file():
                    archive.write(path, path.relative_to(runtime).as_posix())
    with output.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    print(json.dumps({'runtime_archive': str(output), 'sha256': digest}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--driver', action='append', default=[], help='Pinned npm driver, repeatable')
    parser.add_argument('--plugin', action='append', default=[], help='Pinned npm Appium plugin, repeatable')
    args = parser.parse_args()
    build(args.output.resolve(), args.driver, args.plugin)
