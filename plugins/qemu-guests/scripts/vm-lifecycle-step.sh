#!/usr/bin/env bash
# Platform/guest command adapter. No lifecycle locks or cleanup decisions live here.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/vm-utils.sh"
profile="$1"; action="$2"; shift 2
load_profile "$profile"
require_profile_value VM_NAME
require_profile_value SSH_PORT
python_bin="${QEMU_STATE_PYTHON:-$(command -v python || command -v python3)}"
case "$action" in
    describe)
        "$python_bin" -c 'import json,sys; print(json.dumps(dict(zip(sys.argv[1::2],sys.argv[2::2]))))' \
            name "$VM_NAME" vm_dir "$(qemu_native_path "$VM_DIR")" run_dir "$(qemu_native_path "$RUN_DIR")" \
            active_lock "$(qemu_native_path "$ACTIVE_LOCK_DIR")" state_guard "$(qemu_native_path "$STATE_GUARD_DIR")" \
            msys_ps "$(qemu_native_path "${BASH%/*}/ps.exe")" \
            boot_timeout "${BOOT_TIMEOUT:-300}" force "${FORCE:-false}" stop_timeout "${TIMEOUT:-30}";;
    plan)
        for key in VM_MEMORY VM_CPUS DOCKER_DAEMON_PORT TESTCONTAINERS_PORT_START TESTCONTAINERS_PORT_END; do require_profile_value "$key"; done
        QEMU_BIN="$(resolve_qemu)"
        configure_qemu_acceleration "$QEMU_BIN"
        VM_HOME="${VM_DIR}/${VM_NAME}"
        args=(-name "$VM_NAME" "${QEMU_ACCEL_ARGS[@]}" -m "$VM_MEMORY" -smp "$VM_CPUS"
            -drive "file=$(qemu_native_path "${VM_HOME}/disk.qcow2"),format=qcow2,if=virtio"
            -display none -serial "file:$(qemu_native_path "${VM_HOME}/console.log")" -monitor none
            -netdev "$(build_netdev_value)" -device virtio-net-pci,netdev=net0,mac=5a:94:ef:e4:0c:ee)
        "$python_bin" -c 'import json,sys; print(json.dumps(sys.argv[1:]))' "$(qemu_native_path "$QEMU_BIN")" "${args[@]}";;
    network-plan)
        mappings=""
        if [ "$1" != stop ]; then mappings="$(build_forward_mappings)"; fi
        if [ "$1" = start ]; then
            [ -x "$(gvproxy_binary)" ] || { echo 'Error: run setup.sh to install verified gvproxy v0.9.0.' >&2; exit 1; }
        fi
        "$python_bin" -c 'import json,sys; print(json.dumps(dict(zip(sys.argv[1::2],sys.argv[2::2]))))' \
            state "$(qemu_native_path "$(gvproxy_pid_file)")" binary "$(qemu_native_path "$(gvproxy_binary)")" \
            log "$(qemu_native_path "${VM_DIR}/${VM_NAME}/gvproxy.log")" \
            api "${GVPROXY_API_PORT:-19201}" transport "${GVPROXY_QEMU_PORT:-19200}" mappings "$mappings";;
    ssh-ready) ssh_exec 'echo ready' >/dev/null 2>&1;;
    docker-ready) curl --noproxy 127.0.0.1 --connect-timeout 2 --max-time 5 -sf "http://127.0.0.1:${DOCKER_DAEMON_PORT:-2375}/version" >/dev/null 2>&1;;
    pool-ready) verify_docker_publish_pool;;
    poweroff) ssh_exec poweroff;;
    *) echo 'Error: unknown lifecycle adapter action' >&2; exit 2;;
esac
