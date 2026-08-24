#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

pass_count=0

assert_contains() {
    local file="$1"
    local expected="$2"
    local label="$3"
    if grep -Fq "$expected" "$file"; then
        printf '  PASS: %s\n' "$label"
        ((pass_count += 1))
    else
        printf '  FAIL: %s\n' "$label" >&2
        printf 'Expected %s to contain: %s\n' "$file" "$expected" >&2
        exit 1
    fi
}

REPO_DIR="$WORK_DIR/repo"
mkdir -p "$REPO_DIR"
git -C "$REPO_DIR" init -q
git -C "$REPO_DIR" config user.name "Test User"
git -C "$REPO_DIR" config user.email "test@example.invalid"
printf 'before <tag> & value\n' > "$REPO_DIR/example.txt"
git -C "$REPO_DIR" add example.txt
git -C "$REPO_DIR" commit -qm "base"
printf 'after <tag> & value\n' > "$REPO_DIR/example.txt"

MISSING_OUTPUT="$WORK_DIR/missing-output"
(
    cd "$REPO_DIR"
    DIFFTASTIC_COMMAND="missing-difftastic-for-test" \
        "$PLUGIN_DIR/scripts/generate-diff-report.sh" --output-dir "$MISSING_OUTPUT" --base-ref HEAD
)

assert_contains "$MISSING_OUTPUT/diff/index.html" '<select id="diff-renderer">' "renderer selector"
assert_contains "$MISSING_OUTPUT/diff/index.html" '<option value="difftastic" disabled>' "missing Difftastic disabled"
assert_contains "$MISSING_OUTPUT/diff/index.html" '&lt;tag&gt; &amp; value' "Git diff HTML escaping"
assert_contains "$MISSING_OUTPUT/diff/stats.json" '"difftastic_available": false' "missing Difftastic stats"

mkdir -p "$WORK_DIR/fake tools"
FAKE_DIFFT="$WORK_DIR/fake tools/difft"
cat > "$FAKE_DIFFT" <<'EOF'
#!/usr/bin/env bash
if [[ "${DFT_UNSTABLE:-}" != "yes" || "${DFT_DISPLAY:-}" != "json" ]]; then
    exit 1
fi
printf '%s\n' '{"aligned_lines":[[0,0]],"chunks":[[{"lhs":{"line_number":0,"changes":[{"start":7,"end":13,"content":"before","highlight":"normal"}]},"rhs":{"line_number":0,"changes":[{"start":7,"end":12,"content":"after","highlight":"normal"}]}}]],"language":"Text","path":"example.txt","status":"changed"}'
EOF
chmod +x "$FAKE_DIFFT"

AVAILABLE_OUTPUT="$WORK_DIR/available-output"
(
    cd "$REPO_DIR"
    DIFFTASTIC_COMMAND="$FAKE_DIFFT" \
        "$PLUGIN_DIR/scripts/generate-diff-report.sh" --output-dir "$AVAILABLE_OUTPUT" --base-ref HEAD
)

assert_contains "$AVAILABLE_OUTPUT/diff/index.html" '<option value="difftastic">' "available Difftastic selectable"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" 'id="difftastic-json"' "Difftastic JSON payload embedded"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" 'id="difftastic-inline-output"' "inline renderer target"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" 'id="difftastic-side-by-side-output"' "side-by-side renderer target"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" '<select id="difftastic-layout">' "Difftastic layout selector"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" '<option value="side-by-side">Side by side</option>' "side-by-side layout option"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" 'id="difftastic-display-value"' "display mode summary value"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" 'id="difftastic-stats" hidden' "Difftastic-specific summary"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" 'Files Compared' "Difftastic file summary label"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" 'Diff Model' "Difftastic structural summary label"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" 'difftasticStats.hidden = !showDifftastic' "summary switches with renderer"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" "layout.addEventListener('change'" "layout switching script"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" 'function renderStructuralDiff' "custom JSON renderer"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" 'lhsLines: decodeBase64(lhsPayload)' "old source lines embedded"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" 'rhsLines: decodeBase64(rhsPayload)' "new source lines embedded"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" 'text.slice(change.start, change.end)' "safe changed-fragment rendering"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" 'visibleAlignedLines(record, maps)' "context line reconstruction"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" 'structural-change-add' "fragment-only addition styling"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" "renderer.addEventListener('change'" "renderer switching script"
assert_contains "$AVAILABLE_OUTPUT/diff/stats.json" '"difftastic_available": true' "available Difftastic stats"

(
    cd "$REPO_DIR"
    "$PLUGIN_DIR/scripts/generate-report-site.sh" --output-dir "$AVAILABLE_OUTPUT"
)
assert_contains "$AVAILABLE_OUTPUT/index.html" '1 file(s) changed. Git line stats:' "report site stats without jq"

printf '=== Results: %d passed, 0 failed ===\n' "$pass_count"
