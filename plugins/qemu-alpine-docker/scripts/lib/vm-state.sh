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
    vm_state_control stop_qemu
}

vm_state_control() {
    local action="$1"; shift
    local python_bin; python_bin="${QEMU_STATE_PYTHON:-$(command -v python || command -v python3)}"
    if is_windows; then export QEMU_MSYS_PS_BIN="$(qemu_native_path "${BASH%/*}/ps.exe")"; fi
    local -a launcher=()
    [ "${VM_STATE_CONTROL_EXEC:-false}" != true ] || launcher=(exec)
    "${launcher[@]}" "$python_bin" "$(qemu_native_path "${SCRIPT_DIR}/vm-state.py")" "$action" \
        --vm-dir "$(qemu_native_path "$VM_DIR")" --run-dir "$(qemu_native_path "$RUN_DIR")" \
        --active-lock "$(qemu_native_path "$ACTIVE_LOCK_DIR")" --state-guard "$(qemu_native_path "$STATE_GUARD_DIR")" \
        --name "${VM_NAME:-alpine-dev}" --owner "${BASHPID:-$$}" "$@"
}

restore_vm_state_trap() {
    if [ -n "$2" ]; then eval "$2"; else trap - "$1"; fi
}

# The caller knows its token and has cleanup installed before this request.
# Delay shell cancellation until the native creator is joined, so rollback cannot
# race a child which has not yet entered its state transaction. exec makes $! the
# actual creator rather than a disposable shell waiting for native Python.
claim_vm_state() {
    local action="$1" token="$2" owner="$3" child status=0 cancelled=0 previous_int previous_term
    previous_int="$(trap -p INT)"
    previous_term="$(trap -p TERM)"
    trap 'cancelled=130' INT
    trap 'cancelled=143' TERM
    VM_STATE_CONTROL_EXEC=true vm_state_control "$action" --token "$token" --owner "$owner" >/dev/null &
    child=$!
    while true; do
        status=0
        wait "$child" || status=$?
        kill -0 "$child" 2>/dev/null || break
    done
    restore_vm_state_trap INT "$previous_int"
    restore_vm_state_trap TERM "$previous_term"
    [ "$cancelled" -eq 0 ] || return "$cancelled"
    return "$status"
}

# Compatibility for callers with a shell-only callback. Python still owns guard
# acquisition, stale-state refusal, token verification and release.
with_vm_state_guard() {
    local callback="$1"; shift
    (
        local token owner="${BASHPID:-$$}"
        token="$(vm_state_control new-token --owner "$owner")" || return 1
        cleanup_vm_state_guard() {
            local status=$?
            trap - EXIT INT TERM
            vm_state_control guard-release --token "$token" --owner "$owner" || status=1
            exit "$status"
        }
        trap cleanup_vm_state_guard EXIT
        trap 'exit 130' INT
        trap 'exit 143' TERM
        claim_vm_state guard-acquire "$token" "$owner" || exit $?
        "$callback" "$@"
    )
}

acquire_single_vm_lock() { vm_state_control acquire; }
release_single_vm_lock() { vm_state_control release; }
register_vm_process() { vm_state_control register --pid "$1"; }
prepare_vm_launch() { vm_state_control prepare_launch; }
clear_vm_process_state() {
    local -a options=()
    [ "${1:-}" != keep-lock ] || options+=(--keep-lock)
    vm_state_control clear "${options[@]}"
}
release_vm_operation() { vm_state_control end --token "${VM_OPERATION_TOKEN:-}"; }
begin_vm_operation() {
    local owner="${BASHPID:-$$}" token status
    local previous_token="${VM_OPERATION_TOKEN-}" previous_set="${VM_OPERATION_TOKEN+x}"
    local previous_exit previous_int previous_term
    # Do not overwrite this shell's existing cleanup capability, even briefly.
    if [ -n "$previous_token" ] &&
       [ "$(cat "$RUN_DIR/vm-operation.lock/owner.pid" 2>/dev/null || true)" = "$owner" ] &&
       [ "$(cat "$RUN_DIR/vm-operation.lock/token" 2>/dev/null || true)" = "$previous_token" ]; then
        echo 'Error: this shell already owns a VM operation lease.' >&2
        return 1
    fi
    token="$(vm_state_control new-token --owner "$owner")" || return 1
    previous_exit="$(trap -p EXIT)"
    previous_int="$(trap -p INT)"
    previous_term="$(trap -p TERM)"
    export VM_OPERATION_TOKEN="$token"
    if [ "${1:-}" != keep-traps ]; then
        trap release_vm_operation EXIT
        trap 'exit 130' INT
        trap 'exit 143' TERM
    fi
    if claim_vm_state begin "$token" "$owner"; then
        return 0
    else
        status=$?
        release_vm_operation || status=1
        if [ "$previous_set" = x ]; then export VM_OPERATION_TOKEN="$previous_token"; else unset VM_OPERATION_TOKEN; fi
        restore_vm_state_trap EXIT "$previous_exit"
        restore_vm_state_trap INT "$previous_int"
        restore_vm_state_trap TERM "$previous_term"
        return "$status"
    fi
}
