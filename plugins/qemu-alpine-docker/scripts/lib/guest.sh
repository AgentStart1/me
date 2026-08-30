# Guest SSH access and readiness checks.
# Depends on runtime.sh and shared SSH/path variables from ../vm-utils.sh.

ensure_ssh_key() {
    if [ -f "$SSH_KEY" ] && [ -f "${SSH_KEY}.pub" ]; then return 0; fi
    mkdir -p "$(dirname "$SSH_KEY")"
    ssh-keygen -t ed25519 -f "$SSH_KEY" -N "" -q
    echo "Generated SSH key: ${SSH_KEY}" >&2
}

ssh_port() { echo "${SSH_PORT:-2222}"; }

ssh_exec() {
    ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o ConnectTimeout=10 -o BatchMode=yes -p "$(ssh_port)" -i "$SSH_KEY" \
        "root@${SSH_HOST:-127.0.0.1}" "$@"
}

wait_for_ssh() {
    local timeout="${1:-180}" watched_pid="${2:-}" elapsed=0 interval=2
    echo "Waiting for SSH on 127.0.0.1:$(ssh_port) (timeout: ${timeout}s)..." >&2
    while [ "$elapsed" -lt "$timeout" ]; do
        if [ -n "$watched_pid" ] && ! process_is_running "$watched_pid"; then
            echo "Error: QEMU exited before SSH became ready." >&2
            return 1
        fi
        if ssh_exec "echo ready" >/dev/null 2>&1; then
            echo "SSH is ready." >&2
            return 0
        fi
        sleep "$interval"
        elapsed=$((elapsed + interval))
    done
    echo "Error: SSH did not become ready within ${timeout}s." >&2
    return 1
}

wait_for_docker_api() {
    local timeout="${1:-120}" port="${DOCKER_DAEMON_PORT:-2375}" elapsed=0
    while [ "$elapsed" -lt "$timeout" ]; do
        curl -sf "http://127.0.0.1:${port}/version" >/dev/null 2>&1 && return 0
        sleep 2
        elapsed=$((elapsed + 2))
    done
    echo "Error: Docker API did not become ready on 127.0.0.1:${port}." >&2
    return 1
}
