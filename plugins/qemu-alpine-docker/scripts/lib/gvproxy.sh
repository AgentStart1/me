# gvproxy v0.9.0 lifecycle. All control and forwarding sockets bind loopback.
gvproxy_binary() {
    echo "${GVPROXY_BINARY:-${VM_BASE_DIR}/bin/gvproxy$(is_windows && echo .exe)}"
}

install_gvproxy() {
    local asset checksum binary="$(gvproxy_binary)"
    case "$(platform_tag):$(uname -m)" in
        win:x86_64) asset=gvproxy-windows.exe; checksum=41c660f7a9d54018e3b372b8f6aa4d124070bb4b5104d829f8da2171f91a9d22 ;;
        linux:x86_64) asset=gvproxy-linux-amd64; checksum=95c0ee5b5e5d401094ed58ac2f984ba5e935c2cb416c8752329fcfacb721aa9a ;;
        linux:aarch64) asset=gvproxy-linux-arm64; checksum=c1ea864636182a774235c8866c70f2a0223dfcd4f08d24e37a7e82d9882beb9c ;;
        *) echo 'Error: unsupported gvproxy host architecture.' >&2; return 1 ;;
    esac
    if [ -f "$binary" ]; then
        echo "$checksum  $binary" | sha256sum -c - >/dev/null || return 1
        return 0
    fi
    mkdir -p "$(dirname "$binary")"
    local temporary; temporary="$(mktemp "${binary}.download.XXXXXX")"
    if ! curl --fail --location --silent --show-error "https://github.com/containers/gvisor-tap-vsock/releases/download/v0.9.0/${asset}" -o "$temporary" ||
       ! echo "$checksum  $temporary" | sha256sum -c - >/dev/null; then
        rm -f "$temporary"; return 1
    fi
    chmod 0755 "$temporary"
    mv "$temporary" "$binary"
}

gvproxy_pid_file() { echo "${VM_DIR}/${VM_NAME}.gvproxy.pid"; }

# Verify both executable and start time before signalling a persisted native PID.
# The helper uses only Python's standard library (also used by the status panel).
gvproxy_control() {
    local python_bin; python_bin="$(command -v python || command -v python3)"
    "$python_bin" "$(qemu_native_path "${SCRIPT_DIR}/gvproxy-control.py")" "$@"
}

start_gvproxy() {
    local binary="$(gvproxy_binary)"
    build_forward_mappings >/dev/null || return 1
    [ -x "$binary" ] || { echo 'Error: run setup.sh to install verified gvproxy v0.9.0.' >&2; return 1; }
    gvproxy_control start --binary "$(qemu_native_path "$binary")" \
        --state "$(qemu_native_path "$(gvproxy_pid_file)")" \
        --log "$(qemu_native_path "${VM_DIR}/${VM_NAME}/gvproxy.log")" \
        --transport "${GVPROXY_QEMU_PORT:-19200}" --api "${GVPROXY_API_PORT:-19201}"
    local host_port guest_port
    while IFS=: read -r host_port guest_port; do
        gvproxy_api expose "$host_port" "$guest_port" || { stop_gvproxy; return 1; }
    done < <(build_forward_mappings)
}

stop_gvproxy() {
    [ -f "$(gvproxy_pid_file)" ] || return 0
    gvproxy_control stop --state "$(qemu_native_path "$(gvproxy_pid_file)")"
}

check_gvproxy() {
    [ -f "$(gvproxy_pid_file)" ] || { echo 'Error: running VM has no gvproxy state; migrate its network explicitly.' >&2; return 1; }
    build_forward_mappings | gvproxy_control check --api "${GVPROXY_API_PORT:-19201}" \
        --transport "${GVPROXY_QEMU_PORT:-19200}" \
        --state "$(qemu_native_path "$(gvproxy_pid_file)")"
}

gvproxy_api() {
    local action="$1" host_port="$2" guest_port="$3"
    curl --noproxy 127.0.0.1 --fail --silent --show-error --max-time 5 -X POST \
        -H 'Content-Type: application/json' \
        -d "{\"local\":\"127.0.0.1:${host_port}\",\"remote\":\"192.168.127.2:${guest_port}\",\"protocol\":\"tcp\"}" \
        "http://127.0.0.1:${GVPROXY_API_PORT:-19201}/services/forwarder/${action}"
}
