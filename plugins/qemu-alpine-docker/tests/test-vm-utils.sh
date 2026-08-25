#!/bin/bash
# Smoke tests that do not launch QEMU or contact the network.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); echo "  PASS: $1" >&2; }
fail() { FAIL=$((FAIL + 1)); echo "  FAIL: $1" >&2; }
assert_equals() { [ "$1" = "$2" ] && pass "$3" || fail "$3 — expected '$1', got '$2'"; }
assert_contains() { [[ "$2" == *"$1"* ]] && pass "$3" || fail "$3 — '$1' missing"; }
assert_not_contains() { [[ "$2" != *"$1"* ]] && pass "$3" || fail "$3 — unexpected '$1'"; }
assert_file() { [ -f "$1" ] && pass "$2" || fail "$2 — missing $1"; }

MOCK_DIR="$(mktemp -d)"
trap 'rm -rf "$MOCK_DIR"' EXIT
mkdir -p "${MOCK_DIR}/bin" "${MOCK_DIR}/home"

cat > "${MOCK_DIR}/bin/qemu-system-x86_64" <<'MOCK'
#!/bin/bash
echo "QEMU emulator version mock"
MOCK
cat > "${MOCK_DIR}/bin/qemu-img" <<'MOCK'
#!/bin/bash
echo "qemu-img mock"
MOCK
cat > "${MOCK_DIR}/bin/ssh" <<'MOCK'
#!/bin/bash
echo "mock-ssh"
MOCK
cat > "${MOCK_DIR}/bin/ssh-keygen" <<'MOCK'
#!/bin/bash
while [ $# -gt 0 ]; do
    if [ "$1" = "-f" ]; then
        shift
        printf '%s\n' "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI mock-key" > "$1"
        printf '%s\n' "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI mock-key" > "$1.pub"
        exit 0
    fi
    shift
done
exit 1
MOCK
cat > "${MOCK_DIR}/bin/curl" <<'MOCK'
#!/bin/bash
while [ $# -gt 0 ]; do
    if [ "$1" = "-o" ]; then
        shift
        printf '%s\n' mock-content > "$1"
        exit 0
    fi
    shift
done
exit 0
MOCK
cat > "${MOCK_DIR}/bin/rsync" <<'MOCK'
#!/bin/bash
exit 0
MOCK
chmod +x "${MOCK_DIR}/bin/"*

cat > "${MOCK_DIR}/test.profile" <<'PROFILE'
VM_NAME=test-vm
VM_MEMORY=1024
VM_CPUS=1
VM_DISK_SIZE=10G
SSH_PORT=2299
DOCKER_DAEMON_PORT=2375
TESTCONTAINERS_PORT_START=20000
TESTCONTAINERS_PORT_END=20002
PORT_FORWARD=9090:80
PROFILE

export PATH="${MOCK_DIR}/bin:${PATH}"
export QEMU_ALPINE_SKIP_MSYS2_PATH=1
export QEMU_ALPINE_BASE_DIR="${MOCK_DIR}/home"
export HOME="${MOCK_DIR}/home"
# shellcheck source=../scripts/vm-utils.sh
source "${PLUGIN_DIR}/scripts/vm-utils.sh"
VM_DIR="${MOCK_DIR}/vms"
RUN_DIR="${MOCK_DIR}/run"
ACTIVE_LOCK_DIR="${RUN_DIR}/active-vm.lock"
mkdir -p "$VM_DIR"

case "$(platform_tag)" in linux|mac|win|unknown) pass "platform_tag" ;; *) fail "platform_tag" ;; esac
assert_contains "qemu-system-x86_64" "$(resolve_qemu)" "resolve_qemu"
assert_contains "qemu-img" "$(resolve_qemu_img "$(resolve_qemu)")" "resolve_qemu_img"

load_profile "${MOCK_DIR}/test.profile"
assert_equals test-vm "$VM_NAME" "profile VM_NAME"
assert_equals 20002 "$TESTCONTAINERS_PORT_END" "profile range end"

cat > "${MOCK_DIR}/bad.profile" <<'PROFILE'
VM_NAME=$(echo bad)
PROFILE
if load_profile "${MOCK_DIR}/bad.profile" 2>/dev/null; then fail "reject expansion"; else pass "reject expansion"; fi

assert_contains test-vm "$(vm_pid_file)" "PID file contains VM name"
if vm_is_running; then fail "not running without PID"; else pass "not running without PID"; fi
echo "$$" > "$(vm_pid_file)"
if vm_is_running; then pass "running PID detected"; else fail "running PID detected"; fi
rm -f "$(vm_pid_file)"

netdev="$(build_netdev_value)"
assert_contains "hostfwd=tcp:127.0.0.1:2299-:22" "$netdev" "SSH loopback forward"
assert_contains "hostfwd=tcp:127.0.0.1:2375-:2375" "$netdev" "Docker API loopback forward"
assert_contains "hostfwd=tcp:127.0.0.1:20000-:20000" "$netdev" "range first port"
assert_contains "hostfwd=tcp:127.0.0.1:20002-:20002" "$netdev" "range last port"
assert_contains "hostfwd=tcp:127.0.0.1:9090-:80" "$netdev" "custom forward"
assert_not_contains "hostfwd=tcp::" "$netdev" "no wildcard listener"

TESTCONTAINERS_PORT_END=19999
if validate_port_range "$TESTCONTAINERS_PORT_START" "$TESTCONTAINERS_PORT_END" 2>/dev/null; then fail "reject reversed range"; else pass "reject reversed range"; fi
TESTCONTAINERS_PORT_END=20002

acquire_single_vm_lock
echo "$$" > "${ACTIVE_LOCK_DIR}/qemu.pid"
if acquire_single_vm_lock 2>/dev/null; then fail "single VM lock rejects second owner"; else pass "single VM lock rejects second owner"; fi
release_single_vm_lock

rm -f "$SSH_KEY" "${SSH_KEY}.pub"
ensure_ssh_key
assert_file "$SSH_KEY" "private key created"
assert_file "${SSH_KEY}.pub" "public key created"

download_file https://example.invalid/file "${MOCK_DIR}/downloaded"
assert_file "${MOCK_DIR}/downloaded" "download helper target"

start_source="$(<"${PLUGIN_DIR}/scripts/start-vm.sh")"
assert_contains "-accel tcg,thread=multi" "$start_source" "start script uses TCG"
assert_not_contains "whpx" "$start_source" "start script excludes WHPX"
assert_not_contains "enable-kvm" "$start_source" "start script excludes KVM"

testcontainers_source="$(<"${PLUGIN_DIR}/scripts/run-testcontainers.sh")"
assert_contains "TESTCONTAINERS_HOST_OVERRIDE=127.0.0.1" "$testcontainers_source" "host override"
assert_contains "TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock" "$testcontainers_source" "Ryuk guest socket"
assert_not_contains "TESTCONTAINERS_RYUK_DISABLED=true" "$testcontainers_source" "Ryuk remains enabled"

if bash "${PLUGIN_DIR}/scripts/run-testcontainers.sh" >/dev/null 2>"${MOCK_DIR}/usage"; then
    fail "Testcontainers command required"
else
    assert_contains "No test command provided" "$(<"${MOCK_DIR}/usage")" "Testcontainers usage"
fi

echo "=== Results: ${PASS} passed, ${FAIL} failed ===" >&2
[ "$FAIL" -eq 0 ]
