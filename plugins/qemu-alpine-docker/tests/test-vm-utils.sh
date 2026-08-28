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

cat > "${MOCK_DIR}/render.tpl" <<'TEMPLATE'
name={{NAME}}
special={{SPECIAL}}
TEMPLATE
render_template "${MOCK_DIR}/render.tpl" "${MOCK_DIR}/rendered.conf" \
    NAME "vm&one" \
    SPECIAL 'a|b/c\path'
assert_equals $'name=vm&one\nspecial=a|b/c\path' "$(<"${MOCK_DIR}/rendered.conf")" "template replacement is literal"

cat > "${MOCK_DIR}/unresolved.tpl" <<'TEMPLATE'
value={{VALUE}}
missing={{MISSING}}
TEMPLATE
if render_template "${MOCK_DIR}/unresolved.tpl" "${MOCK_DIR}/unresolved.conf" VALUE ok 2>/dev/null; then
    fail "template rejects unresolved placeholder"
else
    pass "template rejects unresolved placeholder"
fi
assert_not_file "${MOCK_DIR}/unresolved.conf" "failed template render leaves no output"

render_template "${PLUGIN_DIR}/templates/setup-alpine.answers.tpl" "${MOCK_DIR}/answers" \
    VM_NAME test-vm \
    FALLBACK_MAIN https://cdn.example/alpine/v3.24/main \
    FALLBACK_COMMUNITY https://cdn.example/alpine/v3.24/community \
    ROOT_SSH_KEY 'ssh-ed25519 mock&key'
assert_contains 'HOSTNAMEOPTS=test-vm' "$(<"${MOCK_DIR}/answers")" "answers template renders VM name"
assert_contains 'ROOTSSHKEY="ssh-ed25519 mock&key"' "$(<"${MOCK_DIR}/answers")" "answers template renders SSH key literally"

render_template "${PLUGIN_DIR}/templates/testcontainers-ports.conf.tpl" "${MOCK_DIR}/ports.conf" \
    TESTCONTAINERS_PORT_START 20000 \
    TESTCONTAINERS_PORT_END 20255
assert_contains 'net.ipv4.ip_local_port_range = 20000 20255' "$(<"${MOCK_DIR}/ports.conf")" "sysctl template renders port range"

render_template "${PLUGIN_DIR}/templates/docker-daemon.json.tpl" "${MOCK_DIR}/daemon.json" \
    DOCKER_GUEST_PORT 2375 \
    DOCKER_DNS_ADDRESS 172.17.0.1
assert_contains 'tcp://0.0.0.0:2375' "$(<"${MOCK_DIR}/daemon.json")" "Docker template renders guest port"
assert_contains '"dns": ["172.17.0.1"]' "$(<"${MOCK_DIR}/daemon.json")" "Docker template selects Unbound on the bridge"

render_template "${PLUGIN_DIR}/templates/unbound.conf.tpl" "${MOCK_DIR}/unbound.conf" \
    DNS_LISTEN_ADDRESS 0.0.0.0 \
    LOCAL_DNS_NETWORK 127.0.0.1/32 \
    DOCKER_DNS_NETWORK 172.17.0.0/16 \
    LOCAL_DNS_PORT 53 \
    QEMU_DNS_ADDRESS 10.0.2.3 \
    QEMU_DNS_PORT 53
assert_contains 'interface: 0.0.0.0' "$(<"${MOCK_DIR}/unbound.conf")" "Unbound listens before the Docker bridge exists"
assert_contains 'access-control: 127.0.0.1/32 allow' "$(<"${MOCK_DIR}/unbound.conf")" "Unbound allows guest loopback"
assert_contains 'access-control: 172.17.0.0/16 allow' "$(<"${MOCK_DIR}/unbound.conf")" "Unbound allows the Docker bridge"
assert_contains 'forward-addr: 10.0.2.3@53' "$(<"${MOCK_DIR}/unbound.conf")" "Unbound forwards to QEMU DNS"
assert_contains 'forward-tcp-upstream: yes' "$(<"${MOCK_DIR}/unbound.conf")" "Unbound forces TCP upstream"

render_template "${PLUGIN_DIR}/templates/use-local-dns.start.tpl" "${MOCK_DIR}/use-local-dns.start" \
    LOCAL_DNS_ADDRESS 127.0.0.1
assert_contains "nameserver %s\\n' '127.0.0.1'" "$(<"${MOCK_DIR}/use-local-dns.start")" "local DNS template selects Unbound"

render_template "${PLUGIN_DIR}/templates/udhcpc.conf.tpl" "${MOCK_DIR}/udhcpc.conf" \
    RESOLV_CONF_MODE no
assert_contains 'RESOLV_CONF="no"' "$(<"${MOCK_DIR}/udhcpc.conf")" "DHCP template preserves local DNS"

render_template "${PLUGIN_DIR}/templates/setup.start.tpl" "${MOCK_DIR}/setup.start" \
    ALPINE_FALLBACK_MIRROR https://dl-cdn.alpinelinux.org/alpine
assert_contains 'ALPINE_FALLBACK_MIRROR="https://dl-cdn.alpinelinux.org/alpine"' "$(<"${MOCK_DIR}/setup.start")" "guest setup template renders fallback mirror"

case "$(platform_tag)" in linux|mac|win|unknown) pass "platform_tag" ;; *) fail "platform_tag" ;; esac
assert_contains "qemu-system-x86_64" "$(resolve_qemu)" "resolve_qemu"
assert_contains "qemu-img" "$(resolve_qemu_img "$(resolve_qemu)")" "resolve_qemu_img"

load_profile "${MOCK_DIR}/test.profile"
assert_equals test-vm "$VM_NAME" "profile VM_NAME"
assert_equals 20002 "$TESTCONTAINERS_PORT_END" "profile range end"

printf 'VM_NAME=crlf-vm\r\nVM_MEMORY=4096\r\n' > "${MOCK_DIR}/crlf.profile"
load_profile "${MOCK_DIR}/crlf.profile"
assert_equals crlf-vm "$VM_NAME" "profile accepts Windows CRLF"
load_profile "${MOCK_DIR}/test.profile"

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
assert_contains 'configure_qemu_acceleration "$QEMU_BIN"' "$start_source" "start script selects the configured accelerator"
assert_contains '"${QEMU_ACCEL_ARGS[@]}"' "$start_source" "start script uses shared acceleration arguments"
assert_not_contains "enable-kvm" "$start_source" "start script excludes KVM"

stop_source="$(<"${PLUGIN_DIR}/scripts/stop-vm.sh")"
assert_contains 'ssh_exec "poweroff"' "$stop_source" "stop script uses Alpine's poweroff command"

create_source="$(<"${PLUGIN_DIR}/scripts/create-vm.sh")"
setup_template="$(<"${PLUGIN_DIR}/templates/setup.start.tpl")"
assert_contains 'configure_qemu_acceleration "$QEMU_BIN"' "$create_source" "provisioning selects the configured accelerator"
assert_contains '"${QEMU_ACCEL_ARGS[@]}"' "$create_source" "provisioning and verification use shared acceleration arguments"
assert_contains "apk add cgroupfs-mount docker docker-cli-compose openssh unbound" "$setup_template" "guest template installs Docker and Unbound"
assert_contains "rc-update add unbound default" "$setup_template" "guest template enables Unbound"
assert_contains "rc-update add local default" "$setup_template" "guest template enables local DNS selection"
assert_contains 'VM_DISK_NATIVE="$(qemu_native_path "$VM_DISK")"' "$create_source" "disk path is converted explicitly"
assert_contains 'MODIFIED_ISO_NATIVE="$(qemu_native_path "$MODIFIED_ISO")"' "$create_source" "ISO path is converted explicitly"
assert_contains 'cp "${SCRIPT_DIR}/select-apk-mirror.sh"' "$create_source" "mirror selector is copied into guest overlay"
assert_contains '/usr/local/libexec/select-apk-mirror' "$setup_template" "guest template runs mirror selector"
assert_contains 'render_template "${TEMPLATE_DIR}/setup-alpine.answers.tpl"' "$create_source" "answers use template rendering"
assert_contains 'render_template "${TEMPLATE_DIR}/testcontainers-ports.conf.tpl"' "$create_source" "sysctl config uses template rendering"
assert_contains 'render_template "${TEMPLATE_DIR}/docker-daemon.json.tpl"' "$create_source" "Docker config uses template rendering"
assert_contains 'render_template "${TEMPLATE_DIR}/unbound.conf.tpl"' "$create_source" "Unbound config uses template rendering"
assert_contains 'render_template "${TEMPLATE_DIR}/use-local-dns.start.tpl"' "$create_source" "local DNS selection uses template rendering"
assert_contains 'render_template "${TEMPLATE_DIR}/udhcpc.conf.tpl"' "$create_source" "DHCP DNS behavior uses template rendering"
assert_contains 'render_template "${TEMPLATE_DIR}/setup.start.tpl"' "$create_source" "guest setup uses template rendering"
assert_not_contains "cat >" "$create_source" "provisioning does not generate product config with heredocs"
assert_not_contains "mirrors.aliyun.com" "$create_source" "provisioning is not tied to Aliyun"
assert_contains "ALPINE_MIRROR_BASE=auto" "$(<"${PLUGIN_DIR}/profiles/dev.profile")" "default profile enables mirror detection"
assert_contains "VM_ACCELERATOR=auto" "$(<"${PLUGIN_DIR}/profiles/dev.profile")" "default profile selects the fastest available accelerator"
assert_contains "VM_MEMORY=4096" "$(<"${PLUGIN_DIR}/profiles/dev.profile")" "default profile provides multi-container memory headroom"
assert_contains "VM_CPUS=4" "$(<"${PLUGIN_DIR}/profiles/dev.profile")" "default profile provides CPU headroom for JVM containers under TCG"
is_windows() { return 0; }
assert_equals "C:/native/disk.qcow2" "$(qemu_native_path "/tmp/disk.qcow2")" "Windows native path conversion"

testcontainers_source="$(<"${PLUGIN_DIR}/scripts/run-testcontainers.sh")"
metrics_source="$(<"${PLUGIN_DIR}/scripts/collect-resource-metrics.ps1")"
assert_contains "TESTCONTAINERS_HOST_OVERRIDE=127.0.0.1" "$testcontainers_source" "host override"
assert_contains "TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock" "$testcontainers_source" "Ryuk guest socket"
assert_contains 'exec env "${COMMAND_ENV[@]}" "$@"' "$testcontainers_source" "Testcontainers environment crosses the MSYS process boundary"
assert_contains 'env "${COMMAND_ENV[@]}" "$@"' "$testcontainers_source" "metrics mode runs the command before producing its summary"
assert_contains 'trap finish_resource_metrics EXIT' "$testcontainers_source" "metrics finalize after successful or failed commands"
assert_contains 'exit "$command_status"' "$testcontainers_source" "metrics preserve the command exit code"
assert_contains 'metrics/latest.json' "$testcontainers_source" "metrics overwrite the stable latest report"
assert_contains 'ConvertTo-Json -Depth 6' "$metrics_source" "metrics report uses structured JSON"
assert_contains 'Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor' "$metrics_source" "metrics sample host CPU"
assert_contains 'head -n 1 /proc/stat' "$metrics_source" "metrics sample guest CPU"
assert_contains '"TEMP=${WINDOWS_TEMP}"' "$testcontainers_source" "Windows tests use a writable native temp directory"
assert_contains '"TMP=${WINDOWS_TEMP}"' "$testcontainers_source" "Windows tests keep TEMP and TMP aligned"
assert_contains 'SOCKET_ENV_EXCLUSION+="TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE"' "$testcontainers_source" "MSYS preserves the guest Docker socket path"
assert_contains '"TESTCONTAINERS_PULL_PAUSE_TIMEOUT=${TESTCONTAINERS_PULL_PAUSE_TIMEOUT_VALUE}"' "$testcontainers_source" "wrapper passes the image pull pause timeout"
assert_contains '"TESTCONTAINERS_PULL_TIMEOUT=${TESTCONTAINERS_PULL_TIMEOUT_VALUE}"' "$testcontainers_source" "wrapper passes the total image pull timeout"
assert_not_contains "TESTCONTAINERS_RYUK_DISABLED=true" "$testcontainers_source" "Ryuk remains enabled"
assert_contains "TESTCONTAINERS_PULL_PAUSE_TIMEOUT=300" "$(<"${PLUGIN_DIR}/profiles/dev.profile")" "default profile tolerates slow TCG layer extraction"
assert_contains "TESTCONTAINERS_PULL_TIMEOUT=1800" "$(<"${PLUGIN_DIR}/profiles/dev.profile")" "default profile allows large image pulls"
assert_contains "TESTCONTAINERS_RESOURCE_METRICS=true" "$(<"${PLUGIN_DIR}/profiles/dev.profile")" "default profile enables resource metrics"
assert_contains "TESTCONTAINERS_RESOURCE_METRICS_INTERVAL=1" "$(<"${PLUGIN_DIR}/profiles/dev.profile")" "default profile samples resource metrics each second"

QEMU_ACCELERATOR=""
QEMU_ACCEL_ARGS=()
VM_ACCELERATOR=tcg
configure_qemu_acceleration "${MOCK_DIR}/bin/qemu-system-x86_64"
assert_equals "tcg" "$QEMU_ACCELERATOR" "explicit TCG selection"
assert_equals "-accel tcg,thread=multi -cpu max" "${QEMU_ACCEL_ARGS[*]}" "TCG uses the full emulated CPU"

qemu_supports_accelerator() { return 0; }
probe_whpx() { return 0; }
VM_ACCELERATOR=auto
configure_qemu_acceleration "${MOCK_DIR}/bin/qemu-system-x86_64"
assert_equals "whpx" "$QEMU_ACCELERATOR" "automatic Windows selection prefers WHPX"
assert_equals "-accel whpx -cpu qemu64" "${QEMU_ACCEL_ARGS[*]}" "WHPX uses its compatible CPU model"

probe_whpx() { return 1; }
configure_qemu_acceleration "${MOCK_DIR}/bin/qemu-system-x86_64"
assert_equals "tcg" "$QEMU_ACCELERATOR" "automatic selection falls back when WHPX probe fails"

VM_ACCELERATOR=invalid
if configure_qemu_acceleration "${MOCK_DIR}/bin/qemu-system-x86_64" >/dev/null 2>"${MOCK_DIR}/invalid-accelerator"; then
    fail "Invalid accelerator should fail"
fi
assert_contains "VM_ACCELERATOR must be auto, whpx, or tcg" "$(<"${MOCK_DIR}/invalid-accelerator")" "invalid accelerator error"

if bash "${PLUGIN_DIR}/scripts/run-testcontainers.sh" >/dev/null 2>"${MOCK_DIR}/usage"; then
    fail "Testcontainers command required"
else
    assert_contains "No test command provided" "$(<"${MOCK_DIR}/usage")" "Testcontainers usage"
fi

cat > "${MOCK_DIR}/invalid-metrics.profile" <<'PROFILE'
VM_NAME=test-vm
SSH_PORT=2299
DOCKER_DAEMON_PORT=2375
TESTCONTAINERS_PORT_START=20000
TESTCONTAINERS_PORT_END=20002
TESTCONTAINERS_RESOURCE_METRICS=maybe
PROFILE
if bash "${PLUGIN_DIR}/scripts/run-testcontainers.sh" --profile "${MOCK_DIR}/invalid-metrics.profile" -- true >/dev/null 2>"${MOCK_DIR}/invalid-metrics"; then
    fail "Invalid metrics switch should fail"
else
    assert_contains "TESTCONTAINERS_RESOURCE_METRICS must be true or false" "$(<"${MOCK_DIR}/invalid-metrics")" "invalid metrics switch error"
fi

cat > "${MOCK_DIR}/invalid-metrics-interval.profile" <<'PROFILE'
VM_NAME=test-vm
SSH_PORT=2299
DOCKER_DAEMON_PORT=2375
TESTCONTAINERS_PORT_START=20000
TESTCONTAINERS_PORT_END=20002
TESTCONTAINERS_RESOURCE_METRICS_INTERVAL=0
PROFILE
if bash "${PLUGIN_DIR}/scripts/run-testcontainers.sh" --profile "${MOCK_DIR}/invalid-metrics-interval.profile" -- true >/dev/null 2>"${MOCK_DIR}/invalid-metrics-interval"; then
    fail "Invalid metrics interval should fail"
else
    assert_contains "TESTCONTAINERS_RESOURCE_METRICS_INTERVAL must be an integer from 1 to 60" "$(<"${MOCK_DIR}/invalid-metrics-interval")" "invalid metrics interval error"
fi

echo "=== Results: ${PASS} passed, ${FAIL} failed ===" >&2
[ "$FAIL" -eq 0 ]
