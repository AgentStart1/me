"""Exercise the production GL snapshot helper on a native hidden SDL context; no VM."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess

from whpx_runtime import msys_root


def run(source, output, msys2=None):
    if os.name != 'nt':
        raise ValueError('The qualified native regression requires a Windows desktop')
    output.mkdir(parents=True, exist_ok=False)
    msys = msys_root(msys2)
    header = source / 'ui/gl-snapshot.h'
    fixture = Path(__file__).resolve().parents[1] / 'tests/viogpu/gl-snapshot.c'
    env = {**os.environ, 'PATH': str(msys / 'ucrt64/bin') + os.pathsep + os.environ['PATH']}
    flags = subprocess.check_output([str(msys / 'ucrt64/bin/pkg-config.exe'),
                                     '--cflags', '--libs', 'sdl2', 'epoxy'], env=env, text=True)
    results = []
    for name, mutate in [('readback', False), ('mutation', True)]:
        includes = source / 'ui'
        if mutate:
            includes = output / 'mutation-header'
            includes.mkdir()
            text = header.read_text()
            token = 'glPixelStorei(GL_PACK_SKIP_PIXELS, 0);'
            if text.count(token) != 1:
                raise ValueError('Unexpected production snapshot helper')
            (includes / header.name).write_text(text.replace(token, 'glPixelStorei(GL_PACK_SKIP_PIXELS, 1);'))
        executable = output / (name + '.exe')
        command = [str(msys / 'ucrt64/bin/gcc.exe'), '-std=c11', '-Wall', '-Wextra',
                   str(fixture), '-I' + str(includes), '-o', str(executable), *shlex.split(flags)]
        with (output / (name + '-build.log')).open('wb') as log:
            subprocess.run(command, env=env, check=True, stdout=log, stderr=subprocess.STDOUT)
        result = subprocess.run([str(executable)], env=env, capture_output=True, timeout=30)
        log = result.stdout + result.stderr
        (output / (name + '.log')).write_bytes(log)
        expected = result.returncode != 0 and b'FAIL' in log if mutate else (
            result.returncode == 0 and b'RESULT 40/40 passed' in log)
        if not expected:
            raise RuntimeError('Native GL snapshot regression failed: ' + name)
        results.append({'case': name, 'negative_control': mutate, 'status': 'PASS'})
    report = {'production_header_sha256': hashlib.sha256(header.read_bytes()).hexdigest(),
              'results': results}
    (output / 'results.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--msys2-root', type=Path)
    args = parser.parse_args()
    run(args.qemu_source.resolve(), args.output.resolve(), args.msys2_root)
