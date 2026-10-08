#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
    echo 'Usage: build-claude-plugin-package.sh --all [--output-dir directory]'
    exit 0
fi
if [[ "${1:-}" != --all ]]; then
    echo 'Expected --all [--output-dir directory]' >&2
    exit 1
fi
shift
exec python3 "$SCRIPT_DIR/build-plugin-packages.py" --client claude "$@"
