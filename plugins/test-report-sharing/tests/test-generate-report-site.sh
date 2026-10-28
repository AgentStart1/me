#!/usr/bin/env bash
set -euo pipefail
PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Only the compatibility boundary belongs here; business contracts live in Python.
bash "$PLUGIN_DIR/scripts/generate-report-site.sh" --help >/dev/null
if bash "$PLUGIN_DIR/scripts/generate-report-site.sh" --invalid-fixture-option >/dev/null 2>&1; then
    echo 'Invalid arguments must propagate a nonzero exit status' >&2
    exit 1
fi
echo 'PASS: help and invalid argument status forwarded'
