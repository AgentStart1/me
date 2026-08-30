# QEMU binary discovery, acceleration selection, and network arguments.
# Depends on runtime.sh and config.sh, loaded earlier by ../vm-utils.sh.

resolve_qemu() {
    local binary="qemu-system-x86_64"
    if command -v "$binary" >/dev/null 2>&1; then
        command -v "$binary"
        return 0
    fi
    local candidate
    local candidates=(
        "/c/Program Files/qemu/${binary}.exe"
        "/c/Program Files (x86)/qemu/${binary}.exe"
        "${LOCALAPPDATA:-}/Programs/qemu/${binary}.exe"
    )
    for candidate in "${candidates[@]}"; do
        if [ -n "$candidate" ] && [ -x "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done
    echo "Error: QEMU ('${binary}') is not installed or not on PATH." >&2
    return 1
}

resolve_qemu_img() {
    local qemu_bin="${1:-$(resolve_qemu)}"
    local sibling="$(dirname "$qemu_bin")/qemu-img"
    [ -x "${sibling}.exe" ] && sibling="${sibling}.exe"
    if [ -x "$sibling" ]; then
        echo "$sibling"
    elif command -v qemu-img >/dev/null 2>&1; then
        command -v qemu-img
    else
        echo "Error: qemu-img is not installed or not on PATH." >&2
        return 1
    fi
}

qemu_supports_accelerator() {
    local qemu_bin="$1" accelerator="$2"
    "$qemu_bin" -accel help 2>/dev/null | grep -qx "$accelerator"
}

probe_whpx() {
    local qemu_bin="$1" probe_pid
    "$qemu_bin" \
        -name qemu-alpine-docker-whpx-probe \
        -accel whpx \
        -cpu qemu64 \
        -machine q35 \
        -m 64 \
        -smp 1 \
        -nodefaults \
        -display none \
        -S >/dev/null 2>&1 &
    probe_pid=$!
    sleep 1
    if ! process_is_running "$probe_pid"; then
        wait "$probe_pid" 2>/dev/null || true
        return 1
    fi
    kill "$probe_pid" 2>/dev/null || true
    wait_for_process_exit "$probe_pid" 5 || kill -9 "$probe_pid" 2>/dev/null || true
}

configure_qemu_acceleration() {
    local qemu_bin="$1" requested="${VM_ACCELERATOR:-auto}"
    case "$requested" in
        auto)
            if is_windows && qemu_supports_accelerator "$qemu_bin" whpx && probe_whpx "$qemu_bin"; then
                QEMU_ACCELERATOR="whpx"
                QEMU_ACCEL_ARGS=(-accel whpx -cpu qemu64)
            else
                QEMU_ACCELERATOR="tcg"
                QEMU_ACCEL_ARGS=(-accel tcg,thread=multi -cpu max)
            fi
            ;;
        whpx)
            is_windows || {
                echo "Error: WHPX acceleration is only supported on Windows." >&2
                return 1
            }
            qemu_supports_accelerator "$qemu_bin" whpx && probe_whpx "$qemu_bin" || {
                echo "Error: WHPX is unavailable. Enable the Windows hypervisor or set VM_ACCELERATOR=tcg." >&2
                return 1
            }
            QEMU_ACCELERATOR="whpx"
            QEMU_ACCEL_ARGS=(-accel whpx -cpu qemu64)
            ;;
        tcg)
            QEMU_ACCELERATOR="tcg"
            QEMU_ACCEL_ARGS=(-accel tcg,thread=multi -cpu max)
            ;;
        *)
            echo "Error: VM_ACCELERATOR must be auto, whpx, or tcg (got '${requested}')." >&2
            return 1
            ;;
    esac
}

build_netdev_value() {
    local ssh_value="${SSH_PORT:-2222}" docker_value="${DOCKER_DAEMON_PORT:-2375}"
    local range_start="${TESTCONTAINERS_PORT_START:-20000}" range_end="${TESTCONTAINERS_PORT_END:-20255}"
    validate_port "$ssh_value" "SSH_PORT"
    validate_port "$docker_value" "DOCKER_DAEMON_PORT"
    validate_port_range "$range_start" "$range_end"
    [ "$ssh_value" != "$docker_value" ] || { echo "Error: SSH and Docker API ports must differ." >&2; return 1; }
    if { [ "$ssh_value" -ge "$range_start" ] && [ "$ssh_value" -le "$range_end" ]; } || \
       { [ "$docker_value" -ge "$range_start" ] && [ "$docker_value" -le "$range_end" ]; }; then
        echo "Error: Fixed SSH/Docker API ports must be outside the Testcontainers range." >&2
        return 1
    fi
    local value="user,id=net0,hostfwd=tcp:127.0.0.1:${ssh_value}-:22,hostfwd=tcp:127.0.0.1:${docker_value}-:2375"
    local port
    for ((port=range_start; port<=range_end; port++)); do
        value+=",hostfwd=tcp:127.0.0.1:${port}-:${port}"
    done
    if [ -n "${PORT_FORWARD:-}" ]; then
        local mapping host_port guest_port
        IFS=',' read -ra mappings <<< "$PORT_FORWARD"
        for mapping in "${mappings[@]}"; do
            [[ "$mapping" =~ ^[0-9]+:[0-9]+$ ]] || { echo "Error: Invalid PORT_FORWARD mapping '${mapping}'." >&2; return 1; }
            host_port="${mapping%%:*}"; guest_port="${mapping##*:}"
            validate_port "$host_port" "PORT_FORWARD host port"
            validate_port "$guest_port" "PORT_FORWARD guest port"
            if [ "$host_port" = "$ssh_value" ] || [ "$host_port" = "$docker_value" ] || \
               { [ "$host_port" -ge "$range_start" ] && [ "$host_port" -le "$range_end" ]; }; then
                echo "Error: PORT_FORWARD host port ${host_port} collides with a reserved port." >&2
                return 1
            fi
            value+=",hostfwd=tcp:127.0.0.1:${host_port}-:${guest_port}"
        done
    fi
    echo "$value"
}
