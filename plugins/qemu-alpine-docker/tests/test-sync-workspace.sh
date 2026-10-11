#!/bin/bash
# Smoke tests that mock SSH and do not launch QEMU or contact the network.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); echo "  PASS: $1" >&2; }
fail() { FAIL=$((FAIL + 1)); echo "  FAIL: $1" >&2; }
assert_contains() {
    if [[ "$2" == *"$1"* ]]; then pass "$3"; else fail "$3 — '$1' missing"; fi
}

MOCK_DIR="$(mktemp -d)"
trap 'rm -rf "$MOCK_DIR"' EXIT
mkdir -p "${MOCK_DIR}/bin" "${MOCK_DIR}/home/vms" "${MOCK_DIR}/source/.git" "${MOCK_DIR}/source/src"
printf 'included\n' > "${MOCK_DIR}/source/src/app.txt"
printf 'excluded\n' > "${MOCK_DIR}/source/.env"
printf 'excluded\n' > "${MOCK_DIR}/source/.git/config"

cat > "${MOCK_DIR}/test.profile" <<'PROFILE'
VM_NAME=test-vm
SSH_PORT=2299
PROFILE
printf '%s\n' "$$" > "${MOCK_DIR}/home/vms/test-vm.pid"
printf 'key\n' > "${MOCK_DIR}/home/id_ed25519"

cat > "${MOCK_DIR}/bin/ssh" <<'MOCK'
#!/bin/bash
printf '%s\n' "$*" >> "$MOCK_SSH_LOG"
case "$*" in
    *"tar -xf -"*) tar -tf - > "$MOCK_ARCHIVE_LOG" ;;
esac
MOCK
cat > "${MOCK_DIR}/bin/python" <<'MOCK'
#!/bin/bash
[[ "$1" == *qemu-control.py ]] || exit 99
exit 0
MOCK
chmod +x "${MOCK_DIR}/bin/python"
chmod +x "${MOCK_DIR}/bin/ssh"

export PATH="${MOCK_DIR}/bin:${PATH}"
export QEMU_ALPINE_SKIP_MSYS2_PATH=1
export QEMU_ALPINE_BASE_DIR="${MOCK_DIR}/home"
export MOCK_SSH_LOG="${MOCK_DIR}/ssh.log"
export MOCK_ARCHIVE_LOG="${MOCK_DIR}/archive.log"

if bash "${PLUGIN_DIR}/scripts/sync-workspace.sh" \
    --profile "${MOCK_DIR}/test.profile" \
    --remote-dir /root/example \
    --exclude coverage \
    "${MOCK_DIR}/source" >/dev/null 2>"${MOCK_DIR}/output"; then
    pass "workspace sync succeeds with mocked SSH"
else
    fail "workspace sync succeeds with mocked SSH"
fi

ssh_log="$(<"${MOCK_DIR}/ssh.log")"
assert_contains "rm -rf '/root/example.new'" "$ssh_log" "sync prepares a staging directory"
assert_contains "tar -xf - -C '/root/example.new'" "$ssh_log" "sync extracts the tar stream remotely"
assert_contains "mv '/root/example.new' '/root/example'" "$ssh_log" "sync replaces the destination after transfer"
assert_contains "Workspace synced" "$(<"${MOCK_DIR}/output")" "sync reports completion"
archive_log="$(<"${MOCK_DIR}/archive.log")"
assert_contains "./src/app.txt" "$archive_log" "sync includes workspace source files"
if [[ "$archive_log" == *"./.env"* || "$archive_log" == *"./.git/"* ]]; then
    fail "sync applies default exclusions"
else
    pass "sync applies default exclusions"
fi

if bash "${PLUGIN_DIR}/scripts/sync-workspace.sh" --remote-dir / "${MOCK_DIR}/source" >/dev/null 2>"${MOCK_DIR}/unsafe"; then
    fail "sync rejects the guest root"
else
    pass "sync rejects the guest root"
fi
assert_contains "Refusing unsafe remote directory" "$(<"${MOCK_DIR}/unsafe")" "unsafe destination error is actionable"

if bash "${PLUGIN_DIR}/scripts/sync-workspace.sh" "${MOCK_DIR}/missing" >/dev/null 2>"${MOCK_DIR}/missing-output"; then
    fail "sync rejects a missing source"
else
    pass "sync rejects a missing source"
fi

echo "=== Results: ${PASS} passed, ${FAIL} failed ===" >&2
[ "$FAIL" -eq 0 ]
