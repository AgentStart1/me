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
assert_not_file() { [ ! -f "$1" ] && pass "$2" || fail "$2 — unexpected $1"; }
assert_not_dir() { [ ! -d "$1" ] && pass "$2" || fail "$2 — unexpected $1"; }

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
cat > "${MOCK_DIR}/bin/cygpath" <<'MOCK'
#!/bin/bash
if [ "${1:-}" = "-m" ]; then shift; fi
printf 'C:/native/%s\n' "${1##*/}"
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
STATE_GUARD_DIR="${RUN_DIR}/vm-state.guard"
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

if validate_image_reference "registry.example/team/my_image:dev"; then pass "image reference allows underscore"; else fail "image reference allows underscore"; fi
if validate_image_reference "image;shutdown" 2>/dev/null; then fail "image reference rejects shell syntax"; else pass "image reference rejects shell syntax"; fi

acquire_single_vm_lock
echo "$$" > "${ACTIVE_LOCK_DIR}/qemu.pid"
if acquire_single_vm_lock 2>/dev/null; then fail "single VM lock rejects second owner"; else pass "single VM lock rejects second owner"; fi
release_single_vm_lock

fail_guarded_update() { return 7; }
if with_vm_state_guard fail_guarded_update 2>/dev/null; then fail "guard propagates callback failure"; else pass "guard propagates callback failure"; fi
assert_not_dir "$STATE_GUARD_DIR" "guard clears after callback failure"

terminate_guarded_update() { kill -TERM "${BASHPID:-$$}"; }
if with_vm_state_guard terminate_guarded_update 2>/dev/null; then fail "guard propagates termination"; else pass "guard propagates termination"; fi
assert_not_dir "$STATE_GUARD_DIR" "guard clears after termination"

cat > "${MOCK_DIR}/lock-contender.sh" <<'CONTENDER'
#!/bin/bash
set -euo pipefail
source "$1"
VM_DIR="$2/race-vms"
RUN_DIR="$2/race-run"
ACTIVE_LOCK_DIR="${RUN_DIR}/active-vm.lock"
STATE_GUARD_DIR="${RUN_DIR}/vm-state.guard"
VM_NAME="$3"
if acquire_single_vm_lock 2>/dev/null; then
    printf '%s\n' won > "$4"
    for ((attempt=0; attempt<500; attempt++)); do
        [ -f "$5" ] && break
        sleep 0.01
    done
    if [ ! -f "$5" ]; then
        printf '%s\n' timeout > "$4"
    fi
    release_single_vm_lock
else
    printf '%s\n' blocked > "$4"
fi
CONTENDER
chmod +x "${MOCK_DIR}/lock-contender.sh"
mkdir -p "${MOCK_DIR}/race-run/active-vm.lock" "${MOCK_DIR}/race-vms"
printf '%s\n' 99999999 > "${MOCK_DIR}/race-run/active-vm.lock/qemu.pid"
printf '%s\n' 99999999 > "${MOCK_DIR}/race-run/active-vm.lock/launcher.pid"
printf '%s\n' stale > "${MOCK_DIR}/race-run/active-vm.lock/vm-name"
bash "${MOCK_DIR}/lock-contender.sh" "${PLUGIN_DIR}/scripts/vm-utils.sh" "$MOCK_DIR" contender-a "${MOCK_DIR}/result-a" "${MOCK_DIR}/result-b" &
contender_a=$!
bash "${MOCK_DIR}/lock-contender.sh" "${PLUGIN_DIR}/scripts/vm-utils.sh" "$MOCK_DIR" contender-b "${MOCK_DIR}/result-b" "${MOCK_DIR}/result-a" &
contender_b=$!
wait "$contender_a"
wait "$contender_b"
race_results="$(<"${MOCK_DIR}/result-a") $(<"${MOCK_DIR}/result-b")"
assert_contains "won" "$race_results" "stale lock race has one winner"
assert_contains "blocked" "$race_results" "stale lock race preserves winner"

mkdir -p "${MOCK_DIR}/home/vms" "${MOCK_DIR}/home/run/active-vm.lock"
printf '%s\n' 99999999 > "${MOCK_DIR}/home/vms/test-vm.pid"
printf '%s\n' 99999999 > "${MOCK_DIR}/home/run/active-vm.lock/qemu.pid"
printf '%s\n' 99999999 > "${MOCK_DIR}/home/run/active-vm.lock/launcher.pid"
printf '%s\n' test-vm > "${MOCK_DIR}/home/run/active-vm.lock/vm-name"
bash "${PLUGIN_DIR}/scripts/stop-vm.sh" "${MOCK_DIR}/test.profile" >/dev/null 2>"${MOCK_DIR}/stop-output"
assert_not_file "${MOCK_DIR}/home/vms/test-vm.pid" "stop clears stale VM PID"
assert_not_dir "${MOCK_DIR}/home/run/active-vm.lock" "stop clears stale global lock"

mkdir -p "${MOCK_DIR}/home/run/active-vm.lock"
printf '%s\n' "$$" > "${MOCK_DIR}/home/run/active-vm.lock/qemu.pid"
printf '%s\n' test-vm > "${MOCK_DIR}/home/run/active-vm.lock/vm-name"
bash "${PLUGIN_DIR}/scripts/stop-vm.sh" "${MOCK_DIR}/test.profile" >/dev/null 2>"${MOCK_DIR}/stop-live-output"
[ -d "${MOCK_DIR}/home/run/active-vm.lock" ] && pass "stop preserves live same-name VM lock" || fail "stop preserves live same-name VM lock"
rm -f "${MOCK_DIR}/home/run/active-vm.lock/qemu.pid" "${MOCK_DIR}/home/run/active-vm.lock/vm-name"
rmdir "${MOCK_DIR}/home/run/active-vm.lock"

mkdir -p "${MOCK_DIR}/home/run/active-vm.lock"
printf '%s\n' "$$" > "${MOCK_DIR}/home/run/active-vm.lock/launcher.pid"
printf '%s\n' test-vm > "${MOCK_DIR}/home/run/active-vm.lock/vm-name"
bash "${PLUGIN_DIR}/scripts/stop-vm.sh" "${MOCK_DIR}/test.profile" >/dev/null 2>"${MOCK_DIR}/stop-launcher-output"
[ -d "${MOCK_DIR}/home/run/active-vm.lock" ] && pass "stop preserves live same-name launcher lock" || fail "stop preserves live same-name launcher lock"
rm -f "${MOCK_DIR}/home/run/active-vm.lock/launcher.pid" "${MOCK_DIR}/home/run/active-vm.lock/vm-name"
rmdir "${MOCK_DIR}/home/run/active-vm.lock"

mkdir -p "${MOCK_DIR}/home/run/active-vm.lock"
printf '%s\n' "$$" > "${MOCK_DIR}/home/run/active-vm.lock/qemu.pid"
printf '%s\n' other-vm > "${MOCK_DIR}/home/run/active-vm.lock/vm-name"
bash "${PLUGIN_DIR}/scripts/stop-vm.sh" "${MOCK_DIR}/test.profile" >/dev/null 2>"${MOCK_DIR}/stop-other-output"
[ -d "${MOCK_DIR}/home/run/active-vm.lock" ] && pass "stop preserves another VM lock" || fail "stop preserves another VM lock"

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

create_source="$(<"${PLUGIN_DIR}/scripts/create-vm.sh")"
assert_contains "apk add cgroupfs-mount docker" "$create_source" "guest installs cgroup service package"
assert_contains 'VM_DISK_NATIVE="$(qemu_native_path "$VM_DISK")"' "$create_source" "disk path is converted explicitly"
assert_contains 'MODIFIED_ISO_NATIVE="$(qemu_native_path "$MODIFIED_ISO")"' "$create_source" "ISO path is converted explicitly"
is_windows() { return 0; }
assert_equals "C:/native/disk.qcow2" "$(qemu_native_path "/tmp/disk.qcow2")" "Windows native path conversion"

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
