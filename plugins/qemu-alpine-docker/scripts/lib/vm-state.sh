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
active_vm_pid() { [ -f "${ACTIVE_LOCK_DIR}/qemu.pid" ] && cat "${ACTIVE_LOCK_DIR}/qemu.pid"; }

vm_state_control() {
    local action="$1"; shift
    local python_bin; python_bin="${QEMU_STATE_PYTHON:-$(command -v python || command -v python3)}"
    if is_windows; then export QEMU_MSYS_PS_BIN="$(qemu_native_path "${BASH%/*}/ps.exe")"; fi
    "$python_bin" "$(qemu_native_path "${SCRIPT_DIR}/vm-state.py")" "$action" \
        --vm-dir "$(qemu_native_path "$VM_DIR")" --run-dir "$(qemu_native_path "$RUN_DIR")" \
        --active-lock "$(qemu_native_path "$ACTIVE_LOCK_DIR")" --state-guard "$(qemu_native_path "$STATE_GUARD_DIR")" \
        --name "${VM_NAME:-alpine-dev}" --owner "${BASHPID:-$$}" "$@"
}

# Compatibility for callers with a shell-only callback. Python still owns guard
# acquisition, stale-state refusal, token verification and release.
with_vm_state_guard() {
    local callback="$1"; shift
    (
        local token owner="${BASHPID:-$$}"
        token="$(vm_state_control guard-acquire --owner "$owner")" || return 1
        cleanup_vm_state_guard() {
            local status=$?
            trap - EXIT INT TERM
            vm_state_control guard-release --token "$token" --owner "$owner" || status=1
            exit "$status"
        }
        trap cleanup_vm_state_guard EXIT
        trap 'exit 130' INT
        trap 'exit 143' TERM
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
    local owner="${BASHPID:-$$}" token
    token="$(vm_state_control begin --owner "$owner")" || return 1
    export VM_OPERATION_TOKEN="$token"
    if [ "${1:-}" != keep-traps ]; then
        trap release_vm_operation EXIT
        trap 'exit 130' INT
        trap 'exit 143' TERM
    fi
}
