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
printf '\033[38;2;255;85;85mDifftastic semantic <change> & output\033[0m\n'
EOF
chmod +x "$FAKE_DIFFT"

AVAILABLE_OUTPUT="$WORK_DIR/available-output"
(
    cd "$REPO_DIR"
    DIFFTASTIC_COMMAND="$FAKE_DIFFT" \
        "$PLUGIN_DIR/scripts/generate-diff-report.sh" --output-dir "$AVAILABLE_OUTPUT" --base-ref HEAD
)

assert_contains "$AVAILABLE_OUTPUT/diff/index.html" '<option value="difftastic">' "available Difftastic selectable"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" '<script src="ansi_up.js"></script>' "bundled ANSI renderer loaded"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" 'id="difftastic-ansi"' "Difftastic ANSI payload embedded"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" 'id="difftastic-stats" hidden' "Difftastic-specific summary"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" 'Files Compared' "Difftastic file summary label"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" 'Diff Model' "Difftastic structural summary label"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" 'difftasticStats.hidden = !showDifftastic' "summary switches with renderer"
assert_contains "$AVAILABLE_OUTPUT/diff/ansi_up.js" 'root.AnsiUp = exp.default' "ansi_up browser bundle"
assert_contains "$AVAILABLE_OUTPUT/diff/ansi_up.js" 'this.VERSION = "6.0.6"' "pinned ansi_up version"
assert_contains "$AVAILABLE_OUTPUT/diff/index.html" "renderer.addEventListener('change'" "renderer switching script"
assert_contains "$AVAILABLE_OUTPUT/diff/stats.json" '"difftastic_available": true' "available Difftastic stats"

(
    cd "$REPO_DIR"
    "$PLUGIN_DIR/scripts/generate-report-site.sh" --output-dir "$AVAILABLE_OUTPUT"
)
assert_contains "$AVAILABLE_OUTPUT/index.html" '1 file(s) changed. Git line stats:' "report site stats without jq"

printf '=== Results: %d passed, 0 failed ===\n' "$pass_count"
