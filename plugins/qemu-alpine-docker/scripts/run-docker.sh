#!/bin/bash
# Execute a Docker CLI command inside the guest over SSH.
#
# This is a convenience wrapper that forwards Docker CLI arguments to the guest VM
# via SSH. It validates that the VM is running and Docker is ready before executing.
#
# Usage: run-docker.sh [--profile <path>] -- <docker arguments...>
#
# Example: run-docker.sh -- ps -a
#          run-docker.sh -- run -d -p 8080:80 nginx
#
# Arguments are shell-escaped before being sent to the guest to prevent injection.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=vm-utils.sh
source "${SCRIPT_DIR}/vm-utils.sh"

PROFILE_ARG=""
while [ $# -gt 0 ]; do
    case "$1" in
        --profile) shift; PROFILE_ARG="${1:-}"; shift ;;
        --profile=*) PROFILE_ARG="${1#*=}"; shift ;;
        --) shift; break ;;
        *) break ;;
    esac
done
[ $# -gt 0 ] || { echo "Usage: $0 [--profile <path>] -- <docker arguments...>" >&2; exit 1; }

load_profile "${PROFILE_ARG:-${PLUGIN_DIR}/profiles/dev.profile}"
require_profile_value VM_NAME
require_profile_value SSH_PORT
vm_is_running || { echo "Error: VM is not running." >&2; exit 1; }
ssh_exec "docker info >/dev/null" || { echo "Error: Docker is not ready in the VM." >&2; exit 1; }

# Build the remote command with shell-escaped arguments.
# This ensures that arguments with special characters (spaces, quotes, etc.)
# are passed correctly to the Docker CLI in the guest.
remote_command="docker"
for arg in "$@"; do
    printf -v escaped '%q' "$arg"
    remote_command+=" ${escaped}"
done
echo "Running in VM: ${remote_command}" >&2
ssh_exec "$remote_command"
