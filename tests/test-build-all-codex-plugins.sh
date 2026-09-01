#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$REPOSITORY_DIR/build/codex"

assert_exists() {
    local path="$1"
    local label="$2"
    if [[ ! -e "$path" ]]; then
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

"$REPOSITORY_DIR/scripts/build-codex-plugin-package.sh" --all

assert_exists "$BUILD_DIR/.agents/plugins/marketplace.json" "generated marketplace"

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
    assert_exists "$BUILD_DIR/plugins/$plugin_name/.codex-plugin/plugin.json" "$plugin_name package"
    assert_contains "$BUILD_DIR/.agents/plugins/marketplace.json" "\"path\": \"./plugins/$plugin_name\"" "$plugin_name marketplace path"
done

if grep -R -Eq '^(context|agent):[[:space:]]*' "$BUILD_DIR/plugins"; then
    echo "FAIL: generated skills retain Claude routing fields" >&2
    exit 1
fi

echo "PASS: generated skills omit Claude routing fields"

if ! git -C "$REPOSITORY_DIR" diff --quiet -- build; then
    echo "FAIL: checked-in build artifacts are not synchronized" >&2
    git -C "$REPOSITORY_DIR" diff --stat -- build >&2
    exit 1
fi

echo "PASS: checked-in build artifacts are synchronized"
