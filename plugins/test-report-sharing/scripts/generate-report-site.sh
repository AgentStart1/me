#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
candidates=(python3 python)
[ -z "${PYTHON_COMMAND:-}" ] || candidates=("$PYTHON_COMMAND")
for candidate in "${candidates[@]}"; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
        exec "$candidate" "$SCRIPT_DIR/generate-report-site.py" "$@"
    fi
done
echo 'Error: Python 3.10+ is required; set PYTHON_COMMAND to a working interpreter.' >&2
exit 1
