#!/bin/bash
# Offline tests for Alpine mirror selection during guest provisioning.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SELECTOR="${PLUGIN_DIR}/scripts/select-apk-mirror.sh"
PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); echo "  PASS: $1" >&2; }
fail() { FAIL=$((FAIL + 1)); echo "  FAIL: $1" >&2; }
assert_equals() { [ "$1" = "$2" ] && pass "$3" || fail "$3 — expected '$1', got '$2'"; }
assert_contains() { [[ "$2" == *"$1"* ]] && pass "$3" || fail "$3 — '$1' missing"; }
assert_not_file() { [ ! -f "$1" ] && pass "$2" || fail "$2 — unexpected $1"; }

MOCK_DIR="$(mktemp -d)"
trap 'rm -rf "$MOCK_DIR"' EXIT
mkdir -p "${MOCK_DIR}/bin"

cat > "${MOCK_DIR}/bin/setup-apkrepos" <<'MOCK'
#!/bin/bash
printf '%s\n' "$*" > "$MOCK_SETUP_LOG"
case "${MOCK_SETUP_RESULT:-ok}" in
    ok) ;;
    empty) exit 0 ;;
    *) exit 1 ;;
esac
printf '%s/v3.24/main\n%s/v3.24/community\n' \
    "${MOCK_FAST_MIRROR:-http://fast.example/alpine}" \
    "${MOCK_FAST_MIRROR:-http://fast.example/alpine}" > "$APK_REPOSITORIES_FILE"
MOCK

cat > "${MOCK_DIR}/bin/apk" <<'MOCK'
#!/bin/bash
repository="$(sed -n '1p' "$APK_REPOSITORIES_FILE")"
printf '%s\n' "$repository" >> "$MOCK_APK_LOG"
case "${MOCK_APK_MODE:-selected}" in
    selected) [[ "$repository" == https://fast.example/alpine/* ]] ;;
    fallback) [[ "$repository" == https://dl-cdn.alpinelinux.org/alpine/* ]] ;;
    manual) [[ "$repository" == https://mirror.example/alpine/* ]] ;;
    fail) exit 1 ;;
    *) exit 1 ;;
esac
MOCK
chmod +x "${MOCK_DIR}/bin/"*

run_selector() {
    local name="$1" base="$2" apk_mode="$3" setup_result="${4:-ok}"
    local case_dir="${MOCK_DIR}/${name}"
    mkdir -p "$case_dir"
    printf '%s\n' 'APKREPOSOPTS="placeholder"' > "${case_dir}/answers"
    PATH="${MOCK_DIR}/bin:${PATH}" \
    APK_REPOSITORIES_FILE="${case_dir}/repositories" \
    ALPINE_SELECTED_MIRROR_FILE="${case_dir}/selected" \
    MOCK_SETUP_LOG="${case_dir}/setup.log" \
    MOCK_APK_LOG="${case_dir}/apk.log" \
    MOCK_APK_MODE="$apk_mode" \
    MOCK_SETUP_RESULT="$setup_result" \
        bash "$SELECTOR" v3.24 "$base" "${case_dir}/answers"
}

selected="$(run_selector fastest auto selected)"
assert_equals "https://fast.example/alpine" "$selected" "auto selects fastest HTTPS mirror"
assert_contains "https://fast.example/alpine/v3.24/main" "$(<"${MOCK_DIR}/fastest/answers")" "auto persists selected mirror"
assert_equals "-cf" "$(<"${MOCK_DIR}/fastest/setup.log")" "auto uses Alpine fastest-mirror detection"

selected="$(run_selector fallback auto fallback)"
assert_equals "https://dl-cdn.alpinelinux.org/alpine" "$selected" "HTTPS validation falls back to official CDN"
assert_contains "https://fast.example/alpine/v3.24/main" "$(<"${MOCK_DIR}/fallback/apk.log")" "fallback first validates selected mirror"
assert_contains "https://dl-cdn.alpinelinux.org/alpine/v3.24/main" "$(<"${MOCK_DIR}/fallback/apk.log")" "fallback validates official CDN"

selected="$(run_selector detection-failure auto fallback fail)"
assert_equals "https://dl-cdn.alpinelinux.org/alpine" "$selected" "detection failure uses official CDN"

selected="$(run_selector empty-result auto fallback empty)"
assert_equals "https://dl-cdn.alpinelinux.org/alpine" "$selected" "empty detection result uses official CDN"

selected="$(run_selector manual https://mirror.example/alpine/ manual)"
assert_equals "https://mirror.example/alpine" "$selected" "manual mirror overrides detection"
assert_not_file "${MOCK_DIR}/manual/setup.log" "manual mirror skips speed detection"
assert_contains "https://mirror.example/alpine/v3.24/community" "$(<"${MOCK_DIR}/manual/answers")" "manual mirror persists to answers"

if run_selector unavailable https://mirror.example/alpine fail >/dev/null 2>&1; then
    fail "unavailable manual mirror is rejected"
else
    pass "unavailable manual mirror is rejected"
fi

if run_selector invalid 'file:///tmp/alpine' manual >/dev/null 2>&1; then
    fail "non-HTTP mirror is rejected"
else
    pass "non-HTTP mirror is rejected"
fi

echo "=== Results: ${PASS} passed, ${FAIL} failed ===" >&2
[ "$FAIL" -eq 0 ]
