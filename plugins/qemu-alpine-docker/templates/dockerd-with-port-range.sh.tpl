#!/bin/sh
# Seed Docker's cached publish range on every execution, including respawns.
set -eu
rm -f /run/qemu-docker-publish-pool.ready
sysctl -w net.ipv4.ip_local_port_range="{{TESTCONTAINERS_PORT_START}} {{TESTCONTAINERS_PORT_END}}" >/dev/null
daemon_pid=
seed_dir=
seed_image=
seed_container=
docker_local() {
    timeout 30 /usr/bin/docker --host unix:///var/run/docker.sock "$@"
}
restore_range() {
    sysctl -w net.ipv4.ip_local_port_range="{{OUTBOUND_PORT_START}} {{OUTBOUND_PORT_END}}" >/dev/null
}
cleanup() {
    status=$?
    trap - EXIT INT TERM
    rm -f /run/qemu-docker-publish-pool.ready
    if [ -n "$seed_container" ]; then docker_local rm -f "$seed_container" >/dev/null || status=1; fi
    if [ -n "$seed_image" ]; then docker_local image rm "$seed_image" >/dev/null || status=1; fi
    if [ -n "$seed_dir" ]; then rm -rf "$seed_dir"; fi
    if [ -n "$daemon_pid" ]; then
        kill "$daemon_pid" 2>/dev/null || true
        remaining=10
        while kill -0 "$daemon_pid" 2>/dev/null && [ "$remaining" -gt 0 ]; do
            sleep 1
            remaining=$((remaining - 1))
        done
        kill -KILL "$daemon_pid" 2>/dev/null || true
        wait "$daemon_pid" 2>/dev/null || true
    fi
    restore_range || status=1
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
/usr/bin/dockerd "$@" &
daemon_pid=$!
elapsed=0
started_at=$(date +%s)
while ! timeout 5 /usr/bin/docker --host unix:///var/run/docker.sock info >/dev/null 2>&1; do
    if ! kill -0 "$daemon_pid" 2>/dev/null; then
        status=0
        wait "$daemon_pid" || status=$?
        daemon_pid=
        [ "$status" -ne 0 ] || status=1
        echo "Error: Docker exited before initializing its publish range." >&2
        exit "$status"
    fi
    if [ "$elapsed" -ge 120 ]; then
        echo "Error: Docker did not initialize within 120 seconds." >&2
        exit 1
    fi
    sleep 1
    elapsed=$(($(date +%s) - started_at))
done
# Existing restored mappings have already initialized the allocator. This also
# avoids needing a spare port when every port in a persistent pool is occupied.
initialized=false
containers=$(docker_local ps -q)
for container in $containers; do
    ports=$(docker_local port "$container")
    if [ -n "$ports" ]; then initialized=true; break; fi
done
if [ "$initialized" = false ]; then
    # Fresh guests need a real mapping, not just API readiness. Import guest
    # BusyBox and its musl loader locally: no registry pull or project image.
    seed_dir=$(mktemp -d)
    tar -chf "$seed_dir/rootfs.tar" -C / bin/busybox lib/ld-musl-x86_64.so.1
    seed_image=$(docker_local import "$seed_dir/rootfs.tar")
    seed_container=$(docker_local run -d --network bridge --publish 127.0.0.1::1 \
        --entrypoint /bin/busybox "$seed_image" sleep 120)
    published=$(docker_local port "$seed_container" 1/tcp)
    published=${published##*:}
    case "$published" in ''|*[!0-9]*) echo "Error: Docker publish pool probe returned no numeric port." >&2; exit 1;; esac
    if [ "$published" -lt {{TESTCONTAINERS_PORT_START}} ] || [ "$published" -gt {{TESTCONTAINERS_PORT_END}} ]; then
        echo "Error: Docker automatically published outside the QEMU forwarding range." >&2
        exit 1
    fi
    docker_local rm -f "$seed_container" >/dev/null
    seed_container=
    docker_local image rm "$seed_image" >/dev/null
    seed_image=
    rm -rf "$seed_dir"
    seed_dir=
fi
restore_range
printf '%s %s\n' '{{TESTCONTAINERS_PORT_START}}' '{{TESTCONTAINERS_PORT_END}}' > /run/qemu-docker-publish-pool.ready
status=0
wait "$daemon_pid" || status=$?
daemon_pid=
exit "$status"
