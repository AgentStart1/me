#!/bin/bash
# Copy a host workspace into the running Alpine guest over SSH.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./vm-utils.sh disable=SC1091
source "${SCRIPT_DIR}/vm-utils.sh"

usage() {
    cat >&2 <<USAGE
Usage: $0 [--profile <path>] [--remote-dir <path>] [--exclude <pattern>] [source]

Copies a local workspace to the running guest through a tar stream over SSH.
The destination is replaced only after a successful transfer. Project
build or test commands remain the caller's responsibility.

Options:
  --profile <path>      Use a non-default VM profile.
  --remote-dir <path>   Guest destination (default: /root/workspace).
  --exclude <pattern>   Add a tar exclusion; may be repeated.
  -h, --help            Show this help and exit.

Default exclusions: .git, target, node_modules, dist, and .env.
USAGE
}

PROFILE_ARG=""
REMOTE_DIR="/root/workspace"
SOURCE_DIR="."
SOURCE_SET=false
EXCLUDES=(.git target node_modules dist .env)

while [ $# -gt 0 ]; do
    case "$1" in
        --profile) shift; PROFILE_ARG="${1:-}"; shift ;;
        --profile=*) PROFILE_ARG="${1#*=}"; shift ;;
        --remote-dir) shift; REMOTE_DIR="${1:-}"; shift ;;
        --remote-dir=*) REMOTE_DIR="${1#*=}"; shift ;;
        --exclude) shift; EXCLUDES+=("${1:-}"); shift ;;
        --exclude=*) EXCLUDES+=("${1#*=}"); shift ;;
        -h|--help) usage; exit 0 ;;
        --) shift; break ;;
        -*) echo "Error: Unknown option: $1" >&2; usage; exit 1 ;;
        *)
            if $SOURCE_SET; then
                echo "Error: Only one source directory may be provided." >&2
                usage
                exit 1
            fi
            SOURCE_DIR="$1"
            SOURCE_SET=true
            shift
            ;;
    esac
done
[ $# -eq 0 ] || { echo "Error: Unexpected positional arguments: $*" >&2; usage; exit 1; }

[ -d "$SOURCE_DIR" ] || { echo "Error: Source directory does not exist: $SOURCE_DIR" >&2; exit 1; }
SOURCE_DIR="$(cd "$SOURCE_DIR" && pwd)"

case "$REMOTE_DIR" in
    /*) ;;
    *) echo "Error: Remote directory must be an absolute path." >&2; exit 1 ;;
esac
[[ "$REMOTE_DIR" =~ ^/[A-Za-z0-9._/-]*$ ]] || {
    echo "Error: Remote directory contains unsupported characters." >&2
    exit 1
}
case "$REMOTE_DIR" in
    /|/root|/home|/usr|/var|/opt|*/..|*/../*|*/.)
        echo "Error: Refusing unsafe remote directory: $REMOTE_DIR" >&2
        exit 1
        ;;
esac

load_profile "${PROFILE_ARG:-${PLUGIN_DIR}/profiles/dev.profile}"
require_profile_value VM_NAME
require_profile_value SSH_PORT
begin_vm_operation
require_known_vm_process
vm_is_running || { echo "Error: VM is not running." >&2; exit 1; }

SSH_HOST="${SSH_HOST:-127.0.0.1}"
SSH_ARGS=(
    -o StrictHostKeyChecking=no
    -o UserKnownHostsFile=/dev/null
    -o BatchMode=yes
    -o ConnectTimeout=10
    -p "$(ssh_port)"
    -i "$SSH_KEY"
    "root@${SSH_HOST}"
)
TAR_EXCLUDES=()
for pattern in "${EXCLUDES[@]}"; do
    [ -n "$pattern" ] || { echo "Error: Exclusion patterns cannot be empty." >&2; exit 1; }
    TAR_EXCLUDES+=("--exclude=$pattern")
done

STAGING_DIR="${REMOTE_DIR}.new"
PREVIOUS_DIR="${REMOTE_DIR}.previous"
echo "Syncing ${SOURCE_DIR} to ${SSH_HOST}:${REMOTE_DIR} ..." >&2
# The validated destination paths are intentionally expanded into remote commands.
# shellcheck disable=SC2029
ssh "${SSH_ARGS[@]}" "rm -rf '$STAGING_DIR' && mkdir -p '$STAGING_DIR'"
# shellcheck disable=SC2029
tar "${TAR_EXCLUDES[@]}" -C "$SOURCE_DIR" -cf - . \
    | ssh "${SSH_ARGS[@]}" "tar -xf - -C '$STAGING_DIR'"
# shellcheck disable=SC2029
ssh "${SSH_ARGS[@]}" \
    "rm -rf '$PREVIOUS_DIR' && if [ -d '$REMOTE_DIR' ]; then mv '$REMOTE_DIR' '$PREVIOUS_DIR'; fi && mv '$STAGING_DIR' '$REMOTE_DIR'"
echo "Workspace synced to ${SSH_HOST}:${REMOTE_DIR}." >&2
