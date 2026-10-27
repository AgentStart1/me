"""Build and run native Windows GPU regressions; never start or modify a VM."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

TESTS = Path(__file__).resolve().parents[1] / 'tests/viogpu'


def run(args):
    if os.name != 'nt':
        raise RuntimeError('This regression recipe requires a Windows host')
    args.output.mkdir(parents=True, exist_ok=False)
    dll = args.virgl_build / 'src/libvirglrenderer-1.dll'
    shutil.copy2(dll, args.output / dll.name)
    includes = [args.virgl_source / path for path in
                ('src', 'src/mesa', 'src/mesa/compat', 'src/mesa/pipe', 'src/gallium/include')]
    includes += [args.virgl_build, args.virgl_build / 'src']
    results = []
    with (args.output / 'build.log').open('wb') as log:
        for name in ('readback', 'read-errors', 'clear-isolation'):
            command = [args.cc, '-std=c11', str(TESTS / (name + '.c')),
                       '-o', str(args.output / (name + '.exe'))]
            if name == 'clear-isolation':
                command += ['-ld3d11', '-ldxgi', '-static-libgcc']
            else:
                command += ['-include', str(args.virgl_build / 'config.h')]
                command += ['-I' + str(path) for path in includes]
                command += ['-L' + str(args.virgl_build / 'src'), '-lvirglrenderer', '-lSDL2']
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    cases = [('readback', [], 0, 'RESULT 24/24 passed'),
             ('read-errors', [], 0, 'RESULT 5/5 passed'),
             ('clear-isolation', ['clear.log', 'warp'], 0, 'RESULT PASS'),
             ('clear-isolation', ['mutation.log', 'warp', 'mutate'], 1, 'mismatches=144')]
    for index, (name, arguments, expected_exit, marker) in enumerate(cases):
        completed = subprocess.run([str(args.output / (name + '.exe')), *arguments],
                                   cwd=args.output, capture_output=True, timeout=120)
        output = completed.stdout + completed.stderr
        (args.output / f'case-{index}.log').write_bytes(output)
        if arguments:
            output += (args.output / arguments[0]).read_bytes()
        if completed.returncode != expected_exit or marker.encode() not in output:
            raise RuntimeError('GPU regression failed: ' + name)
        results.append({'case': name, 'negative_control': expected_exit != 0, 'status': 'PASS'})
    report = {'dll_sha256': hashlib.sha256(dll.read_bytes()).hexdigest(), 'results': results}
    (args.output / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--virgl-source', type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument('--virgl-build', type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument('--output', type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument('--cc', default='gcc')
    run(parser.parse_args())
