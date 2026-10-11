#!/bin/bash
# Start the single persistent Alpine Docker VM in the background.
#
# This script launches the already-provisioned VM (created by create-vm.sh)
# in the background with full port forwarding enabled. It waits for SSH and
# Docker API to become available before reporting success.
#
# Prerequisites:
#   - The VM must already be provisioned (create-vm.sh must have run)
#   - The VM must not already be running (idempotent check)
#
# The script acquires the global singleton lock to ensure only one VM runs at a time.
# It sets up a cleanup handler that kills the QEMU process if the script fails
# before the VM is fully started (e.g., SSH timeout).
#
# Port forwarding:
#   - SSH: localhost:SSH_PORT → guest:22
#   - Docker API: localhost:DOCKER_DAEMON_PORT → guest:2375
#   - Testcontainers: localhost:PORT_START-END → guest:PORT_START-END
#   - Custom PORT_FORWARD mappings from the profile
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=vm-utils.sh
source "${SCRIPT_DIR}/vm-utils.sh"

# --- Load and validate profile ---
PROFILE_ARG="${1:-${PLUGIN_DIR}/profiles/dev.profile}"
load_profile "$PROFILE_ARG"
for key in VM_NAME VM_MEMORY VM_CPUS SSH_PORT DOCKER_DAEMON_PORT TESTCONTAINERS_PORT_START TESTCONTAINERS_PORT_END; do
    require_profile_value "$key"
done

begin_vm_operation
require_known_vm_process

# --- Per-VM file paths ---
VM_HOME="${VM_DIR}/${VM_NAME}"
VM_DISK="${VM_HOME}/disk.qcow2"
READY_FILE="$(vm_ready_file)"
CONSOLE_LOG="${VM_HOME}/console.log"
CONSOLE_LOG_NATIVE="$(qemu_native_path "$CONSOLE_LOG")"
BOOT_TIMEOUT="${BOOT_TIMEOUT:-300}"

# --- Pre-flight checks ---
[ -f "$VM_DISK" ] || { echo "Error: VM disk not found. Run create-vm.sh first." >&2; exit 1; }
[ -f "$READY_FILE" ] || { echo "Error: VM has not passed provisioning verification." >&2; exit 1; }

# --- Idempotency check ---
if vm_is_running; then
    check_gvproxy
    wait_for_ssh "$BOOT_TIMEOUT" "$(vm_pid)"
    wait_for_docker_api 120
    ssh_exec "grep -qx 'net.ipv4.ip_local_port_range = ${TESTCONTAINERS_PORT_START} ${TESTCONTAINERS_PORT_END}' /etc/sysctl.d/99-testcontainers-ports.conf"
    wait_for_docker_publish_pool
    qemu_control record --pid "$(vm_pid)" --name "$VM_NAME" --state "$(qemu_native_path "$(vm_identity_file)")"
    echo "VM '${VM_NAME}' is already running (PID $(vm_pid))." >&2
    exit 0
fi

# --- Acquire lock and configure acceleration ---
QEMU_BIN="$(resolve_qemu)"
configure_qemu_acceleration "$QEMU_BIN"
NETDEV_VALUE="$(build_netdev_value)"
acquire_single_vm_lock

# --- Cleanup handler ---
# If the script exits before the VM is fully started, kill the QEMU process
# and clear the VM state. The STARTED flag ensures we don't clean up after success.
QEMU_PID=""
STARTED=false
cleanup_start_failure() {
    local status=$?
    trap - EXIT
    if [ "$STARTED" != "true" ]; then
        if process_is_running "${QEMU_PID:-}"; then
            stop_qemu_process || status=1
        fi
        if process_is_running "${QEMU_PID:-}"; then
            echo 'Error: QEMU is still running; retaining its network and ownership state.' >&2
            status=1
        else
            if stop_gvproxy; then
                clear_vm_process_state || status=1
            else
                echo 'Error: gvproxy cleanup failed; retaining the VM reservation.' >&2
                status=1
            fi
        fi
    fi
    release_vm_operation || status=1
    exit "$status"
}
trap cleanup_start_failure EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

start_gvproxy

# --- QEMU arguments ---
# The VM runs with the same acceleration and resource settings as during provisioning.
# Port forwarding is configured via the -netdev argument (build_netdev_value).
qemu_args=(
    -name "$VM_NAME"
    "${QEMU_ACCEL_ARGS[@]}"
    -m "$VM_MEMORY"
    -smp "$VM_CPUS"
    -drive "file=${VM_DISK},format=qcow2,if=virtio"
    -display none
    -serial "file:${CONSOLE_LOG_NATIVE}"
    -monitor none
    -netdev "$NETDEV_VALUE"
    -device virtio-net-pci,netdev=net0,mac=5a:94:ef:e4:0c:ee
)

# --- Launch VM ---
echo "Starting VM '${VM_NAME}' with ${QEMU_ACCELERATOR} acceleration and gvproxy networking..." >&2
"$QEMU_BIN" "${qemu_args[@]}" </dev/null >>"${VM_HOME}/qemu.log" 2>&1 &
QEMU_PID=$!
register_vm_process "$QEMU_PID"

# Wait for the guest to boot and services to be ready
wait_for_ssh "$BOOT_TIMEOUT" "$QEMU_PID"
wait_for_docker_api 120
ssh_exec "grep -qx 'net.ipv4.ip_local_port_range = ${TESTCONTAINERS_PORT_START} ${TESTCONTAINERS_PORT_END}' /etc/sysctl.d/99-testcontainers-ports.conf" || {
    echo "Error: Guest Docker publish range differs from this profile. Update the stopped guest's port configuration before starting; changing QEMU forwards alone does not update Docker's cached range." >&2
    exit 1
}
wait_for_docker_publish_pool

# --- Success ---
STARTED=true
trap release_vm_operation EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
echo "VM '${VM_NAME}' is ready in the background (PID ${QEMU_PID})." >&2
echo "Docker API: tcp://127.0.0.1:${DOCKER_DAEMON_PORT}" >&2
echo "Testcontainers ports: 127.0.0.1:${TESTCONTAINERS_PORT_START}-${TESTCONTAINERS_PORT_END}" >&2
echo "Console log: ${CONSOLE_LOG}" >&2
