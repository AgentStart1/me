"""Bundle the canonical scoped-command owner into independent plugins."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ('android-emulator-profile', 'diff-sharing', 'test-report-sharing')
FILES = ('command_tree.py', 'command-worker.py')


def sync(check=False):
    for plugin in PLUGINS:
        for name in FILES:
            source = (ROOT / 'scripts/process-runtime' / name).read_bytes()
            target = ROOT / 'plugins' / plugin / 'scripts' / name
            if check:
                if not target.is_file() or target.read_bytes() != source:
                    raise SystemExit(f'Outdated command runtime: {target}')
            else:
                target.write_bytes(source)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    sync(parser.parse_args().check)
