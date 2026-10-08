#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=vm-utils.sh
source "$SCRIPT_DIR/vm-utils.sh"
PROFILE_ARG=""
while [ $# -gt 0 ]; do
    case "$1" in
        --profile) [ $# -ge 2 ] || { echo "Error: --profile requires a path." >&2; exit 1; }; PROFILE_ARG="$2"; shift 2 ;;
        --profile=*) PROFILE_ARG="${1#*=}"; shift ;;
        -h|--help) echo "Usage: $0 [--profile <path>]"; exit 0 ;;
        *) echo "Error: Unknown argument: $1" >&2; exit 1 ;;
    esac
done
load_profile "${PROFILE_ARG:-${PLUGIN_DIR}/profiles/dev.profile}"
require_profile_value VM_NAME
require_profile_value SSH_PORT
vm_is_running || { echo "Error: VM is not running. Start it before compiling the proxy." >&2; exit 1; }
PROXY_NAME=docker
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) TARGET_OS=windows; TARGET_ARCH=amd64; PROXY_NAME=docker.exe ;;
    Linux*) TARGET_OS=linux ;;
    Darwin*) TARGET_OS=darwin ;;
    *) echo "Error: Unsupported host platform." >&2; exit 1 ;;
esac
if [ "$TARGET_OS" != windows ]; then
    case "$(uname -m)" in
        x86_64|amd64) TARGET_ARCH=amd64 ;;
        aarch64|arm64) TARGET_ARCH=arm64 ;;
        *) echo "Error: Unsupported host architecture." >&2; exit 1 ;;
    esac
fi
PROXY_DIR=${QEMU_DOCKER_PROXY_DIR:-"$PLUGIN_DIR/../../build/qemu-docker-proxy"}
mkdir -p "$PROXY_DIR"
PROXY_DIR="$(cd "$PROXY_DIR" && pwd)"
GUEST_DIR=""
LOCAL_TEMP=""
cleanup() {
    local status=$?
    trap - EXIT
    [ -z "$LOCAL_TEMP" ] || rm -f -- "$LOCAL_TEMP"
    if [ -n "$GUEST_DIR" ]; then
        ssh_exec "rm -rf -- '$GUEST_DIR'" </dev/null || echo "Warning: guest proxy cleanup failed." >&2
    fi
    exit "$status"
}
trap cleanup EXIT
GUEST_CANDIDATE="$(ssh_exec 'mktemp -d /tmp/qemu-docker-proxy.XXXXXXXXXX' </dev/null)"
[[ "$GUEST_CANDIDATE" =~ ^/tmp/qemu-docker-proxy\.[A-Za-z0-9]+$ ]] || { echo "Error: Invalid guest staging directory." >&2; exit 1; }
GUEST_DIR="$GUEST_CANDIDATE"
echo "Compiling Docker proxy in Alpine for ${TARGET_OS}/${TARGET_ARCH} ..." >&2
tar -C "$SCRIPT_DIR/docker-proxy" -cf - . -C "$PLUGIN_DIR/templates" build-docker-proxy.sh.tpl \
    | ssh_exec "tar -xf - -C '$GUEST_DIR'"
# Windows checkouts may use CRLF; normalize the guest script before invoking ash.
ssh_exec "cd '$GUEST_DIR' && tr -d '\015' < build-docker-proxy.sh.tpl > guest-build.sh && ash ./guest-build.sh '$TARGET_OS' '$TARGET_ARCH'" </dev/null
LOCAL_TEMP="$(mktemp "$PROXY_DIR/.docker-proxy.XXXXXXXXXX")"
ssh_exec "cat '$GUEST_DIR/proxy-bin'" </dev/null > "$LOCAL_TEMP"
[ -s "$LOCAL_TEMP" ] || { echo "Error: Empty proxy download." >&2; exit 1; }
chmod +x "$LOCAL_TEMP"
mv -f -- "$LOCAL_TEMP" "$PROXY_DIR/$PROXY_NAME"
LOCAL_TEMP=""
echo "Docker proxy compiled and downloaded." >&2
