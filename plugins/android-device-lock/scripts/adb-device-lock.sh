#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
candidates=(python3 python)
[ -z "${ANDROID_DEVICE_LOCK_PYTHON:-}" ] || candidates=("$ANDROID_DEVICE_LOCK_PYTHON")
for candidate in "${candidates[@]}"; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
        MSYS2_ARG_CONV_EXCL="/data/local/tmp" exec "$candidate" "$SCRIPT_DIR/adb-device-lock.py" "$@"
    fi
done
echo 'Error: Python 3.10+ is required; set ANDROID_DEVICE_LOCK_PYTHON to a working interpreter.' >&2
exit 1
