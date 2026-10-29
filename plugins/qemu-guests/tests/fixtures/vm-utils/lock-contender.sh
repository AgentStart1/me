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
