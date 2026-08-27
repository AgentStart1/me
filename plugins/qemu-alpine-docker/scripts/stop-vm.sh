#!/bin/bash
# stop-vm.sh — Gracefully shut down the Alpine VM.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=vm-utils.sh
source "${SCRIPT_DIR}/vm-utils.sh"

# Load profile
PROFILE_ARG="${1:-}"
if [ -n "$PROFILE_ARG" ]; then
    load_profile "$PROFILE_ARG"
else
    load_profile "${PLUGIN_DIR}/profiles/dev.profile"
fi

require_profile_value VM_NAME
require_profile_value SSH_PORT

VM_NAME="${VM_NAME:-alpine-dev}"
SSH_PORT="${SSH_PORT:-2222}"
FORCE="${FORCE:-false}"
TIMEOUT="${TIMEOUT:-30}"

# Check if running
if ! vm_is_running; then
    echo "VM '${VM_NAME}' is not running." >&2
    clear_vm_process_state
    exit 0
fi

QEMU_PID="$(vm_pid)"
echo "Stopping VM '${VM_NAME}' (PID: ${QEMU_PID})..." >&2

if [ "$FORCE" = "true" ]; then
    echo "Force stopping VM..." >&2
    kill -9 "$QEMU_PID" 2>/dev/null || true
    wait_for_process_exit "$QEMU_PID" 10 || true
    clear_vm_process_state
    echo "VM '${VM_NAME}' force stopped." >&2
    exit 0
fi

# Try ACPI shutdown via SSH first
echo "Attempting graceful ACPI shutdown..." >&2
ssh_exec "shutdown -h now" 2>/dev/null || true

# Wait for process to exit
elapsed=0
while kill -0 "$QEMU_PID" 2>/dev/null && [ "$elapsed" -lt "$TIMEOUT" ]; do
    sleep 1
    elapsed=$((elapsed + 1))
done

if kill -0 "$QEMU_PID" 2>/dev/null; then
    echo "Graceful shutdown timed out after ${TIMEOUT}s. Force stopping..." >&2
    kill -9 "$QEMU_PID" 2>/dev/null || true
fi

wait "$QEMU_PID" 2>/dev/null || true
clear_vm_process_state
echo "VM '${VM_NAME}' stopped." >&2
