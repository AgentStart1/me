"""Bundle the canonical report runtime into independently installable plugins."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sync(check=False):
    source = (ROOT / 'scripts/report-sharing/report_runtime.py').read_bytes()
    for name in ('diff-sharing', 'test-report-sharing'):
        target = ROOT / 'plugins' / name / 'scripts/report_runtime.py'
        if check:
            if target.read_bytes() != source:
                raise SystemExit(f'Outdated runtime: {target}; run scripts/sync-report-runtime.py')
        else:
            target.write_bytes(source)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    sync(parser.parse_args().check)
