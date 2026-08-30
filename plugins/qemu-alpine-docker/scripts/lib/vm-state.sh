# Per-VM process state and globally serialized single-VM locking.
# Depends on runtime.sh and state directory variables from ../vm-utils.sh.

vm_pid_file() { echo "${VM_DIR}/${VM_NAME:-alpine-dev}.pid"; }
vm_ready_file() { echo "${VM_DIR}/${VM_NAME:-alpine-dev}/ready"; }
vm_pid() { [ -f "$(vm_pid_file)" ] && cat "$(vm_pid_file)"; }
vm_is_running() { local pid; pid="$(vm_pid 2>/dev/null || true)"; process_is_running "$pid"; }
active_vm_pid() { [ -f "${ACTIVE_LOCK_DIR}/qemu.pid" ] && cat "${ACTIVE_LOCK_DIR}/qemu.pid"; }

with_vm_state_guard() {
    local callback="$1"
    local state_guard_caller_pid="${BASHPID:-$$}"
    shift
    mkdir -p "$RUN_DIR"
    (
        local attempts=0 owner_pid pending_signal="" guard_owned=false
        cleanup_vm_state_guard() {
            if [ "$guard_owned" = "true" ]; then
                rm -f "${STATE_GUARD_DIR}/owner.pid"
                rmdir "$STATE_GUARD_DIR" 2>/dev/null || true
            fi
        }
        trap cleanup_vm_state_guard EXIT
        trap 'pending_signal=130' INT
        trap 'pending_signal=143' TERM
        while ! mkdir "$STATE_GUARD_DIR" 2>/dev/null; do
            [ -z "$pending_signal" ] || exit "$pending_signal"
            owner_pid="$(cat "${STATE_GUARD_DIR}/owner.pid" 2>/dev/null || true)"
            if [ -n "$owner_pid" ] && ! process_is_running "$owner_pid"; then
                echo "Error: stale VM state guard at ${STATE_GUARD_DIR}; remove it after confirming no plugin script is running." >&2
                return 1
            fi
            attempts=$((attempts + 1))
            if [ "$attempts" -ge 100 ]; then
                echo "Error: timed out waiting for the VM state guard at ${STATE_GUARD_DIR}." >&2
                return 1
            fi
            sleep 0.05
        done
        guard_owned=true
        trap 'exit 130' INT
        trap 'exit 143' TERM
        [ -z "$pending_signal" ] || exit "$pending_signal"
        echo "${BASHPID:-$$}" > "${STATE_GUARD_DIR}/owner.pid" || return 1
        "$callback" "$@"
    )
}

acquire_single_vm_lock_guarded() {
    if mkdir "$ACTIVE_LOCK_DIR" 2>/dev/null; then
        echo "${VM_NAME:-unknown}" > "${ACTIVE_LOCK_DIR}/vm-name"
        echo "$state_guard_caller_pid" > "${ACTIVE_LOCK_DIR}/launcher.pid"
        return 0
    fi
    local active_pid active_launcher active_name
    active_pid="$(active_vm_pid 2>/dev/null || true)"
    active_launcher="$(cat "${ACTIVE_LOCK_DIR}/launcher.pid" 2>/dev/null || true)"
    active_name="$(cat "${ACTIVE_LOCK_DIR}/vm-name" 2>/dev/null || echo unknown)"
    local owner_pid=""
    if process_is_running "$active_pid"; then
        owner_pid="$active_pid"
    elif process_is_running "$active_launcher"; then
        owner_pid="$active_launcher"
    fi
    if [ -n "$owner_pid" ]; then
        echo "Error: VM '${active_name}' already owns the global lock (PID ${owner_pid})." >&2
        return 1
    fi
    rm -f "${ACTIVE_LOCK_DIR}/qemu.pid" "${ACTIVE_LOCK_DIR}/launcher.pid" "${ACTIVE_LOCK_DIR}/vm-name"
    if ! rmdir "$ACTIVE_LOCK_DIR" 2>/dev/null || ! mkdir "$ACTIVE_LOCK_DIR" 2>/dev/null; then
        echo "Error: failed to replace stale VM lock at ${ACTIVE_LOCK_DIR}." >&2
        return 1
    fi
    echo "${VM_NAME:-unknown}" > "${ACTIVE_LOCK_DIR}/vm-name"
    echo "$state_guard_caller_pid" > "${ACTIVE_LOCK_DIR}/launcher.pid"
}

acquire_single_vm_lock() { with_vm_state_guard acquire_single_vm_lock_guarded; }

register_vm_process() {
    local pid="$1"
    echo "$pid" > "$(vm_pid_file)"
    echo "$pid" > "${ACTIVE_LOCK_DIR}/qemu.pid"
}

release_single_vm_lock_guarded() {
    rm -f "${ACTIVE_LOCK_DIR}/qemu.pid" "${ACTIVE_LOCK_DIR}/launcher.pid" "${ACTIVE_LOCK_DIR}/vm-name"
    rmdir "$ACTIVE_LOCK_DIR" 2>/dev/null || true
}

release_single_vm_lock() { with_vm_state_guard release_single_vm_lock_guarded; }

clear_vm_process_state_guarded() {
    rm -f "$(vm_pid_file)"
    local active_name active_pid active_launcher current_launcher
    active_name="$(cat "${ACTIVE_LOCK_DIR}/vm-name" 2>/dev/null || true)"
    active_pid="$(active_vm_pid 2>/dev/null || true)"
    active_launcher="$(cat "${ACTIVE_LOCK_DIR}/launcher.pid" 2>/dev/null || true)"
    current_launcher="$state_guard_caller_pid"
    if [ "$active_name" = "${VM_NAME:-}" ] && \
       ! process_is_running "$active_pid" && \
       { [ "$active_launcher" = "$current_launcher" ] || ! process_is_running "$active_launcher"; }; then
        rm -f "${ACTIVE_LOCK_DIR}/qemu.pid" "${ACTIVE_LOCK_DIR}/launcher.pid" "${ACTIVE_LOCK_DIR}/vm-name"
        rmdir "$ACTIVE_LOCK_DIR" 2>/dev/null || true
    fi
}

clear_vm_process_state() { with_vm_state_guard clear_vm_process_state_guarded; }
