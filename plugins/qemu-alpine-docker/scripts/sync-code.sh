#!/bin/bash
# Sync a host directory to the guest.
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
SRC_DIR="${1:-.}"
DEST_DIR="${2:-/root/project}"
[[ "$DEST_DIR" =~ ^/[A-Za-z0-9._/-]+$ ]] || { echo "Error: Invalid guest destination." >&2; exit 1; }

load_profile "${PROFILE_ARG:-${PLUGIN_DIR}/profiles/dev.profile}"
require_profile_value VM_NAME
require_profile_value SSH_PORT
vm_is_running || { echo "Error: VM is not running." >&2; exit 1; }
[ -d "$SRC_DIR" ] || { echo "Error: Source directory not found: ${SRC_DIR}" >&2; exit 1; }
SRC_DIR="$(cd "$SRC_DIR" && pwd)"

ssh_exec "mkdir -p '${DEST_DIR}'"
echo "Syncing ${SRC_DIR} -> VM:${DEST_DIR}" >&2
rsync_to_vm "$SRC_DIR" "$DEST_DIR"
