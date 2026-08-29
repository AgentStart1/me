#!/bin/bash
# Connect to the guest through an interactive SSH or SFTP session.
#
# This script provides interactive access to the running VM. By default, it opens
# an SSH session; use --sftp for file transfer mode.
#
# The SSH key, loopback host, and port are resolved from the plugin profile
# the same way the rest of the scripts do. This ensures consistency across
# all scripts (create-vm.sh, start-vm.sh, run-docker.sh, etc.).
#
# This script was renamed from sync-code.sh to better reflect its purpose
# (it's a general-purpose VM connection tool, not just for code sync).
#
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

# --- Parse arguments ---
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

# --- Load profile and validate ---
load_profile "${PROFILE_ARG:-${PLUGIN_DIR}/profiles/dev.profile}"
require_profile_value VM_NAME
require_profile_value SSH_PORT
vm_is_running || { echo "Error: VM is not running." >&2; exit 1; }

# --- Open connection ---
# Use exec to replace the current process with the SSH/SFTP client.
# This avoids leaving a shell wrapper process running.
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
