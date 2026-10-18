#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT


snapshot_path() {
    python3 - "$1" <<'PY'
import json,sys
from pathlib import Path
path=Path(sys.argv[1])
for root in (path,*path.parents):
    pointer=root/'current.json'
    if pointer.is_file():
        path=root/'generations'/json.loads(pointer.read_text())['generation']/path.relative_to(root)
        break
print(path.as_posix())
PY
}

assert_contains() {
    local path; path="$(snapshot_path "$1")"
    local expected="$2"
    if ! grep -Fq "$expected" "$path"; then
        echo "Expected $path to contain: $expected" >&2
        exit 1
    fi
}

assert_not_contains() {
    local path; path="$(snapshot_path "$1")"
    local unexpected="$2"
    if grep -Fq "$unexpected" "$path"; then
        echo "Expected $path not to contain: $unexpected" >&2
        exit 1
    fi
}

OUTPUT_DIR="$WORK_DIR/report-site"
"$PLUGIN_DIR/scripts/generate-report-site.sh" --output-dir "$OUTPUT_DIR"

assert_contains "$OUTPUT_DIR/index.html" 'No reports found. Run your tests first to generate reports.'
assert_not_contains "$OUTPUT_DIR/index.html" 'Code Diff'
assert_not_contains "$PLUGIN_DIR/templates/report-site.html" '@@DIFF_SECTION@@'

echo "=== Results: 3 passed, 0 failed ==="
