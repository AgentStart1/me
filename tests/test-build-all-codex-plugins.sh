#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_DIR="$(dirname "$SCRIPT_DIR")"
TEST_ROOT="$(mktemp -d)"
OUTPUT_DIR="$TEST_ROOT/me.codex"

cleanup() {
    rm -rf "$TEST_ROOT"
}
trap cleanup EXIT

assert_exists() {
    local path="$1"
    local label="$2"
    if [[ ! -e "$path" ]]; then
        printf 'FAIL: %s\n' "$label" >&2
        exit 1
    fi
    printf 'PASS: %s\n' "$label"
}

assert_not_exists() {
    local path="$1"
    local label="$2"
    if [[ -e "$path" ]]; then
        printf 'FAIL: %s\n' "$label" >&2
        exit 1
    fi
    printf 'PASS: %s\n' "$label"
}

assert_contains() {
    local path="$1"
    local expected="$2"
    local label="$3"
    if ! grep -Fq "$expected" "$path"; then
        printf 'FAIL: %s\n' "$label" >&2
        exit 1
    fi
    printf 'PASS: %s\n' "$label"
}

mkdir -p "$OUTPUT_DIR"
printf 'preserve me\n' > "$OUTPUT_DIR/unrelated.txt"
mkdir -p "$OUTPUT_DIR/plugins/stale-plugin" "$OUTPUT_DIR/.agents/plugins"
printf 'stale\n' > "$OUTPUT_DIR/plugins/stale-plugin/stale.txt"
printf 'stale\n' > "$OUTPUT_DIR/.agents/plugins/stale.txt"

"$REPOSITORY_DIR/scripts/build-codex-plugin-package.sh" --all --output-dir "$OUTPUT_DIR"

assert_exists "$OUTPUT_DIR/.agents/plugins/marketplace.json" "generated marketplace"
assert_exists "$OUTPUT_DIR/README.md" "generated Codex README"
assert_exists "$OUTPUT_DIR/unrelated.txt" "unrelated target file is preserved"
assert_not_exists "$OUTPUT_DIR/plugins/stale-plugin" "stale generated plugin is replaced"
assert_not_exists "$OUTPUT_DIR/.agents/plugins/stale.txt" "stale marketplace content is replaced"

for plugin_name in \
    android-appium-device-lock \
    android-profile \
    client-ui-best-practices \
    diff-sharing \
    general-coding-practices \
    kotlin-coding-practices \
    qemu-alpine-docker \
    recyclerview-best-practice \
    test-report-sharing; do
    assert_exists "$OUTPUT_DIR/plugins/$plugin_name/.codex-plugin/plugin.json" "$plugin_name package"
    assert_contains "$OUTPUT_DIR/.agents/plugins/marketplace.json" "\"path\": \"./plugins/$plugin_name\"" "$plugin_name marketplace path"
done

if grep -R -Eq '^(context|agent):[[:space:]]*' "$OUTPUT_DIR/plugins"; then
    echo "FAIL: generated skills retain Claude routing fields" >&2
    exit 1
fi

echo "PASS: generated skills omit Claude routing fields"
