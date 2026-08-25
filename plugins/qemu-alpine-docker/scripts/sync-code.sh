#!/bin/bash
# Open an interactive SSH or SFTP session to the guest.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=vm-utils.sh
source "${SCRIPT_DIR}/vm-utils.sh"

usage() {
    cat >&2 <<USAGE
Usage: $0 [--profile <path>] [--sftp]

Opens an interactive SSH session to the guest by default. Pass --sftp to open
an SFTP session instead. The SSH key, loopback host, and port are resolved from
the plugin profile the same way the rest of the scripts do.

Options:
  --profile <path>   Use a non-default profile (default: ${PLUGIN_DIR}/profiles/dev.profile).
  --profile=<path>   Same as --profile <path>.
  --sftp             Open an SFTP session instead of an interactive SSH shell.
  -h, --help         Show this help and exit.
USAGE
}

PROFILE_ARG=""
MODE="ssh"
while [ $# -gt 0 ]; do
    case "$1" in
        --profile) shift; PROFILE_ARG="${1:-}"; shift ;;
        --profile=*) PROFILE_ARG="${1#*=}"; shift ;;
        --sftp) MODE="sftp"; shift ;;
        -h|--help) usage; exit 0 ;;
        --) shift; break ;;
        *) echo "Error: Unknown argument: $1" >&2; usage; exit 1 ;;
    esac
done
[ $# -eq 0 ] || { echo "Error: Unexpected positional arguments: $*" >&2; usage; exit 1; }

load_profile "${PROFILE_ARG:-${PLUGIN_DIR}/profiles/dev.profile}"
require_profile_value VM_NAME
require_profile_value SSH_PORT
vm_is_running || { echo "Error: VM is not running." >&2; exit 1; }

SSH_HOST="${SSH_HOST:-127.0.0.1}"
case "$MODE" in
    ssh)  echo "Opening SSH session to VM '${VM_NAME}' on ${SSH_HOST}:$(ssh_port)" >&2 ;;
    sftp) echo "Opening SFTP session to VM '${VM_NAME}' on ${SSH_HOST}:$(ssh_port)" >&2 ;;
esac

case "$MODE" in
    ssh)
        exec ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
            -o ConnectTimeout=10 -p "$(ssh_port)" -i "$SSH_KEY" \
            "root@${SSH_HOST}"
        ;;
    sftp)
        exec sftp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
            -o ConnectTimeout=10 -P "$(ssh_port)" -i "$SSH_KEY" \
            "root@${SSH_HOST}"
        ;;
esac
