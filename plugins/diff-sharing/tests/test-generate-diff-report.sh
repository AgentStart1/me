#!/usr/bin/env bash
set -euo pipefail
PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Only the compatibility boundary belongs here; business contracts live in Python.
for script in generate-diff-report generate-diff-site; do
    bash "$PLUGIN_DIR/scripts/$script.sh" --help >/dev/null
    if bash "$PLUGIN_DIR/scripts/$script.sh" --invalid-fixture-option >/dev/null 2>&1; then
        echo "$script: invalid arguments must propagate a nonzero exit status" >&2
        exit 1
    fi
done
echo 'PASS: help and invalid argument status forwarded'
