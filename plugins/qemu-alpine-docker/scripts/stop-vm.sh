#!/bin/bash
# stop-vm.sh — Gracefully shut down the Alpine VM.
#
# Shutdown strategy:
#   1. If FORCE=true, immediately kill the QEMU process (SIGKILL).
#   2. Otherwise, send "poweroff" to the guest via SSH (ACPI shutdown).
#   3. Wait up to TIMEOUT seconds (default: 30s) for the process to exit.
#   4. If the process doesn't exit, force-kill it.
#
# The script clears the VM state (PID file and global lock) after shutdown.
# It also handles the case where the VM is not running (clears stale state).
#
# Environment variables:
#   FORCE  — if "true", skip graceful shutdown (default: false)
#   TIMEOUT — seconds to wait for graceful shutdown (default: 30)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=vm-utils.sh
source "${SCRIPT_DIR}/vm-utils.sh"

# --- Load profile ---
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

# --- Check if running ---
# If the VM is not running, clean up any stale state and exit.
if ! vm_is_running; then
    echo "VM '${VM_NAME}' is not running." >&2
    clear_vm_process_state
    exit 0
fi

QEMU_PID="$(vm_pid)"
echo "Stopping VM '${VM_NAME}' (PID: ${QEMU_PID})..." >&2

# --- Force stop mode ---
if [ "$FORCE" = "true" ]; then
    echo "Force stopping VM..." >&2
    kill -9 "$QEMU_PID" 2>/dev/null || true
    wait_for_process_exit "$QEMU_PID" 10 || true
    clear_vm_process_state
    echo "VM '${VM_NAME}' force stopped." >&2
    exit 0
fi

# --- Graceful shutdown ---
# Send "poweroff" to the guest via SSH. This triggers the Alpine shutdown sequence.
# If SSH is not available, we'll fall through to the force-kill logic.
echo "Attempting graceful ACPI shutdown..." >&2
ssh_exec "poweroff" 2>/dev/null || true

# Wait for the QEMU process to exit naturally.
elapsed=0
while kill -0 "$QEMU_PID" 2>/dev/null && [ "$elapsed" -lt "$TIMEOUT" ]; do
    sleep 1
    elapsed=$((elapsed + 1))
done

# If the process is still running after the timeout, force-kill it.
if kill -0 "$QEMU_PID" 2>/dev/null; then
    echo "Graceful shutdown timed out after ${TIMEOUT}s. Force stopping..." >&2
    kill -9 "$QEMU_PID" 2>/dev/null || true
fi

# Wait for the process to exit and clean up state.
wait "$QEMU_PID" 2>/dev/null || true
clear_vm_process_state
echo "VM '${VM_NAME}' stopped." >&2
