# Per-VM process state and globally serialized single-VM locking.
# Depends on runtime.sh and state directory variables from ../vm-utils.sh.

vm_pid_file() { echo "${VM_DIR}/${VM_NAME:-alpine-dev}.pid"; }
vm_ready_file() { echo "${VM_DIR}/${VM_NAME:-alpine-dev}/ready"; }
vm_pid() { [ -f "$(vm_pid_file)" ] && cat "$(vm_pid_file)"; }
vm_identity_file() { echo "${VM_DIR}/${VM_NAME:-alpine-dev}.qemu.json"; }
qemu_control() {
    local python_bin; python_bin="$(command -v python || command -v python3)"
    if is_windows; then
        export QEMU_MSYS_PS_BIN="$(qemu_native_path "${BASH%/*}/ps.exe")"
    fi
    "$python_bin" "$(qemu_native_path "${SCRIPT_DIR}/qemu-control.py")" "$@"
}
vm_process_probe() {
    local pid; pid="$(vm_pid 2>/dev/null || true)"
    [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
    qemu_control probe --pid "$pid" --name "$VM_NAME" --state "$(qemu_native_path "$(vm_identity_file)")"
}
vm_is_running() { vm_process_probe; }
require_known_vm_process() {
    local status=0
    vm_process_probe || status=$?
    [ "$status" -le 1 ] || { echo 'Error: QEMU identity inspection failed; refusing lifecycle changes.' >&2; return 1; }
}
stop_qemu_process() {
    local pid; pid="$(vm_pid 2>/dev/null || true)"
    [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 0
    qemu_control stop --pid "$pid" --name "$VM_NAME" --state "$(qemu_native_path "$(vm_identity_file)")"
}
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
    if [ -n "$active_name" ] && [ -f "${VM_DIR}/${active_name}.gvproxy.pid" ]; then
        echo "Error: VM '${active_name}' retains gvproxy state; stop that VM before another launch." >&2
        return 1
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
    if ! qemu_control record --pid "$pid" --name "$VM_NAME" --state "$(qemu_native_path "$(vm_identity_file)")"; then
        kill "$pid" 2>/dev/null || true
        wait_for_process_exit "$pid" 10 || kill -9 "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
        return 1
    fi
}

release_single_vm_lock_guarded() {
    rm -f "${ACTIVE_LOCK_DIR}/qemu.pid" "${ACTIVE_LOCK_DIR}/launcher.pid" "${ACTIVE_LOCK_DIR}/vm-name"
    rmdir "$ACTIVE_LOCK_DIR" 2>/dev/null || true
}

release_single_vm_lock() { with_vm_state_guard release_single_vm_lock_guarded; }

clear_vm_process_state_guarded() {
    rm -f "$(vm_pid_file)" "$(vm_identity_file)"
    local active_name active_pid active_launcher current_launcher
    active_name="$(cat "${ACTIVE_LOCK_DIR}/vm-name" 2>/dev/null || true)"
    active_pid="$(active_vm_pid 2>/dev/null || true)"
    active_launcher="$(cat "${ACTIVE_LOCK_DIR}/launcher.pid" 2>/dev/null || true)"
    current_launcher="$state_guard_caller_pid"
    if [ "${1:-}" = keep-lock ]; then
        [ "$active_name" != "${VM_NAME:-}" ] || rm -f "${ACTIVE_LOCK_DIR}/qemu.pid"
        return 0
    fi
    if [ "$active_name" = "${VM_NAME:-}" ] && \
       ! process_is_running "$active_pid" && \
       { [ "$active_launcher" = "$current_launcher" ] || ! process_is_running "$active_launcher"; }; then
        rm -f "${ACTIVE_LOCK_DIR}/qemu.pid" "${ACTIVE_LOCK_DIR}/launcher.pid" "${ACTIVE_LOCK_DIR}/vm-name"
        rmdir "$ACTIVE_LOCK_DIR" 2>/dev/null || true
    fi
}

clear_vm_process_state() { with_vm_state_guard clear_vm_process_state_guarded "$@"; }

acquire_vm_operation_guarded() {
    local operation_dir="${RUN_DIR}/vm-operation.lock" token="$1"
    if [ -d "$operation_dir" ]; then
        echo 'Error: VM lifecycle operation is busy or interrupted. Inspect vm-operation.lock; remove it only after confirming all lifecycle scripts have exited.' >&2
        return 1
    fi
    mkdir "$operation_dir"
    printf '%s\n' "$state_guard_caller_pid" > "$operation_dir/owner.pid"
    printf '%s\n' "$token" > "$operation_dir/token"
    printf '%s\n' "$VM_NAME" > "$operation_dir/vm-name"
}

release_vm_operation_guarded() {
    local operation_dir="${RUN_DIR}/vm-operation.lock"
    [ -d "$operation_dir" ] || return 0
    if [ "$(cat "$operation_dir/owner.pid" 2>/dev/null || true)" = "$state_guard_caller_pid" ] &&
       [ "$(cat "$operation_dir/token" 2>/dev/null || true)" = "${VM_OPERATION_TOKEN:-}" ]; then
        rm -f "$operation_dir/owner.pid" "$operation_dir/token" "$operation_dir/vm-name"
        rmdir "$operation_dir"
    fi
}

release_vm_operation() { with_vm_state_guard release_vm_operation_guarded; }
begin_vm_operation() {
    local token="${BASHPID:-$$}-${RANDOM}-${RANDOM}"
    with_vm_state_guard acquire_vm_operation_guarded "$token" || return 1
    export VM_OPERATION_TOKEN="$token"
    if [ "${1:-}" != keep-traps ]; then
        trap release_vm_operation EXIT
        trap 'exit 130' INT
        trap 'exit 143' TERM
    fi
}
