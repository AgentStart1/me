#!/usr/bin/env bash
set -euo pipefail
PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fixture="$(mktemp -d)"
trap 'rm -rf "$fixture"' EXIT

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

cd "$fixture"
mkdir -p build/reports/tests/test/classes build/test-results/test extra/nested
printf '<html>root report</html>' > build/reports/tests/test/index.html
printf '<html>nested report</html>' > build/reports/tests/test/classes/index.html
printf '<testsuite name="first"/>' > build/test-results/test/TEST-same.xml
printf '<testsuite name="second"/>' > extra/nested/TEST-same.xml
REPORT_DIRS="$fixture/build/reports/tests/test:$fixture/extra" \
    bash "$PLUGIN_DIR/scripts/collect-test-results.sh" --output-dir "$fixture/output"
published="$(snapshot_path "$fixture/output")"
jq -e '.total_reports == 1 and .xml_files == 2' "$published/reports/summary.json" >/dev/null
[ "$(find "$published/test-results" -name '*.xml' | wc -l | tr -d ' ')" = 2 ]
grep -l first "$published"/test-results/*.xml >/dev/null
grep -l second "$published"/test-results/*.xml >/dev/null
bash "$PLUGIN_DIR/scripts/generate-report-site.sh" --output-dir "$fixture/output"
published="$(snapshot_path "$fixture/output")"
[ "$(grep -c '(JUnit XML)' "$published/index.html")" = 2 ]
mkdir empty
cd empty
bash "$PLUGIN_DIR/scripts/collect-test-results.sh" --output-dir "$fixture/empty-output"
jq -e '.total_reports == 0 and .xml_files == 0 and .report_directories == []' "$(snapshot_path "$fixture/empty-output/reports/summary.json")" >/dev/null
echo 'PASS: nested XML retained without collisions, legacy directory alias, HTML deduplication, XML links and empty summary'
