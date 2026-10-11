# Guest SSH access and readiness checks.
# Depends on runtime.sh and shared SSH/path variables from ../vm-utils.sh.

ensure_ssh_key() {
    if [ -f "$SSH_KEY" ] && [ -f "${SSH_KEY}.pub" ]; then return 0; fi
    mkdir -p "$(dirname "$SSH_KEY")"
    if [ -f "$SSH_KEY" ]; then
        ssh-keygen -y -P "" -f "$SSH_KEY" > "${SSH_KEY}.pub.tmp" || {
            rm -f "${SSH_KEY}.pub.tmp"
            return 1
        }
        mv "${SSH_KEY}.pub.tmp" "${SSH_KEY}.pub"
        return 0
    fi
    if [ -f "${SSH_KEY}.pub" ]; then
        echo 'Error: SSH public key exists without its private key; refusing to replace it.' >&2
        return 1
    fi
    ssh-keygen -t ed25519 -f "$SSH_KEY" -N "" -q || return 1
    echo "Generated SSH key: ${SSH_KEY}" >&2
}

ssh_port() { echo "${SSH_PORT:-2222}"; }

ssh_exec() {
    ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o ConnectTimeout=10 -o ServerAliveInterval=5 -o ServerAliveCountMax=3 \
        -o BatchMode=yes -p "$(ssh_port)" -i "$SSH_KEY" \
        "root@${SSH_HOST:-127.0.0.1}" "$@"
}

wait_for_ssh() {
    local timeout="${1:-180}" watched_pid="${2:-}" interval=2 deadline
    deadline=$((SECONDS + timeout))
    echo "Waiting for SSH on 127.0.0.1:$(ssh_port) (timeout: ${timeout}s)..." >&2
    while [ "$SECONDS" -lt "$deadline" ]; do
        if [ -n "$watched_pid" ] && ! process_is_running "$watched_pid"; then
            echo "Error: QEMU exited before SSH became ready." >&2
            return 1
        fi
        if ssh_exec "echo ready" >/dev/null 2>&1; then
            echo "SSH is ready." >&2
            return 0
        fi
        sleep "$interval"
    done
    echo "Error: SSH did not become ready within ${timeout}s." >&2
    return 1
}

wait_for_docker_api() {
    local timeout="${1:-120}" port="${DOCKER_DAEMON_PORT:-2375}" deadline
    deadline=$((SECONDS + timeout))
    while [ "$SECONDS" -lt "$deadline" ]; do
        curl --noproxy 127.0.0.1 --connect-timeout 2 --max-time 5 -sf "http://127.0.0.1:${port}/version" >/dev/null 2>&1 && return 0
        sleep 2
    done
    echo "Error: Docker API did not become ready on 127.0.0.1:${port}." >&2
    return 1
}

wait_for_docker_publish_pool() {
    local deadline=$((SECONDS + 180))
    # Existing guests without the wrapper retain their old startup behavior.
    while [ "$SECONDS" -lt "$deadline" ]; do
        if ssh_exec "test ! -x /usr/local/libexec/dockerd-with-port-range || grep -qx '${TESTCONTAINERS_PORT_START} ${TESTCONTAINERS_PORT_END}' /run/qemu-docker-publish-pool.ready" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    echo "Error: Docker did not verify its publish pool and restore outbound ports; inspect the guest Docker service log." >&2
    return 1
}
