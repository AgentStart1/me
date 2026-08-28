#!/bin/bash
# Start the single persistent Alpine Docker VM in the background.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=vm-utils.sh
source "${SCRIPT_DIR}/vm-utils.sh"

PROFILE_ARG="${1:-${PLUGIN_DIR}/profiles/dev.profile}"
load_profile "$PROFILE_ARG"
for key in VM_NAME VM_MEMORY VM_CPUS SSH_PORT DOCKER_DAEMON_PORT TESTCONTAINERS_PORT_START TESTCONTAINERS_PORT_END; do
    require_profile_value "$key"
done

VM_HOME="${VM_DIR}/${VM_NAME}"
VM_DISK="${VM_HOME}/disk.qcow2"
READY_FILE="$(vm_ready_file)"
CONSOLE_LOG="${VM_HOME}/console.log"
CONSOLE_LOG_NATIVE="$(qemu_native_path "$CONSOLE_LOG")"
BOOT_TIMEOUT="${BOOT_TIMEOUT:-300}"

[ -f "$VM_DISK" ] || { echo "Error: VM disk not found. Run create-vm.sh first." >&2; exit 1; }
[ -f "$READY_FILE" ] || { echo "Error: VM has not passed provisioning verification." >&2; exit 1; }

if vm_is_running; then
    echo "VM '${VM_NAME}' is already running (PID $(vm_pid))." >&2
    exit 0
fi

QEMU_BIN="$(resolve_qemu)"
configure_qemu_acceleration "$QEMU_BIN"
NETDEV_VALUE="$(build_netdev_value)"
acquire_single_vm_lock

QEMU_PID=""
STARTED=false
cleanup_start_failure() {
    if [ "$STARTED" != "true" ]; then
        if process_is_running "${QEMU_PID:-}"; then
            kill "$QEMU_PID" 2>/dev/null || true
            wait_for_process_exit "$QEMU_PID" 10 || kill -9 "$QEMU_PID" 2>/dev/null || true
        fi
        clear_vm_process_state
    fi
}
trap cleanup_start_failure EXIT INT TERM

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
    -device virtio-net-pci,netdev=net0
)

echo "Starting VM '${VM_NAME}' with ${QEMU_ACCELERATOR} acceleration and QEMU user networking..." >&2
"$QEMU_BIN" "${qemu_args[@]}" &
QEMU_PID=$!
register_vm_process "$QEMU_PID"

wait_for_ssh "$BOOT_TIMEOUT" "$QEMU_PID"
wait_for_docker_api 120

STARTED=true
trap - EXIT INT TERM
echo "VM '${VM_NAME}' is ready in the background (PID ${QEMU_PID})." >&2
echo "Docker API: tcp://127.0.0.1:${DOCKER_DAEMON_PORT}" >&2
echo "Testcontainers ports: 127.0.0.1:${TESTCONTAINERS_PORT_START}-${TESTCONTAINERS_PORT_END}" >&2
echo "Console log: ${CONSOLE_LOG}" >&2
