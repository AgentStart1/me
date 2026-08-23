#!/bin/bash
# Run a host test command against Docker inside the QEMU guest.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=vm-utils.sh
source "${SCRIPT_DIR}/vm-utils.sh"

PROFILE_ARG=""
VERBOSE=false
while [ $# -gt 0 ]; do
    case "$1" in
        --profile) shift; PROFILE_ARG="${1:-}"; shift ;;
        --profile=*) PROFILE_ARG="${1#*=}"; shift ;;
        --verbose|-v) VERBOSE=true; shift ;;
        --) shift; break ;;
        *) break ;;
    esac
done

if [ $# -eq 0 ]; then
    echo "Error: No test command provided." >&2
    echo "Usage: $0 [--profile <path>] [--verbose] -- <command> [args...]" >&2
    exit 1
fi

load_profile "${PROFILE_ARG:-${PLUGIN_DIR}/profiles/dev.profile}"
for key in VM_NAME SSH_PORT DOCKER_DAEMON_PORT TESTCONTAINERS_PORT_START TESTCONTAINERS_PORT_END; do
    require_profile_value "$key"
done
validate_port_range "$TESTCONTAINERS_PORT_START" "$TESTCONTAINERS_PORT_END"

if ! vm_is_running; then
    echo "Error: VM '${VM_NAME}' is not running. Start it first." >&2
    exit 1
fi
wait_for_docker_api 30

export DOCKER_HOST="tcp://127.0.0.1:${DOCKER_DAEMON_PORT}"
unset DOCKER_TLS_VERIFY DOCKER_CERT_PATH DOCKER_SOCKET
export TESTCONTAINERS_HOST_OVERRIDE=127.0.0.1
export TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock
# Ryuk runs inside the guest and cleans test resources through the mounted guest socket.
unset TESTCONTAINERS_RYUK_DISABLED

if [ "$VERBOSE" = "true" ]; then
    echo "DOCKER_HOST=${DOCKER_HOST}" >&2
    echo "TESTCONTAINERS_HOST_OVERRIDE=${TESTCONTAINERS_HOST_OVERRIDE}" >&2
    echo "Published port range=${TESTCONTAINERS_PORT_START}-${TESTCONTAINERS_PORT_END}" >&2
    echo "Ryuk=enabled" >&2
fi

echo "Running Testcontainers command: $*" >&2
exec "$@"
