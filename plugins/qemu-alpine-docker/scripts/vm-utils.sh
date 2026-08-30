#!/bin/bash
# Compatibility facade for shared QEMU Alpine Docker shell utilities.
#
# Every command script sources this file. It owns the shared path variables and
# loads the implementation modules in dependency order so callers keep one
# stable entrypoint.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Resolve home directory; on Windows/MSYS2, prefer USERPROFILE via cygpath.
HOME_DIR="${HOME:-/home/$(id -un)}"
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
        if [ -n "${USERPROFILE:-}" ] && command -v cygpath >/dev/null 2>&1; then
            HOME_DIR="$(cygpath -u "$USERPROFILE")"
        fi
        ;;
esac

# Directory layout under QEMU_ALPINE_BASE_DIR (~/.qemu-alpine-docker).
VM_BASE_DIR="${QEMU_ALPINE_BASE_DIR:-${HOME_DIR}/.qemu-alpine-docker}"
IMAGES_DIR="${VM_BASE_DIR}/images"
VM_DIR="${VM_BASE_DIR}/vms"
RUN_DIR="${VM_BASE_DIR}/run"
ACTIVE_LOCK_DIR="${RUN_DIR}/active-vm.lock"
STATE_GUARD_DIR="${RUN_DIR}/vm-state.guard"
SSH_KEY="${VM_BASE_DIR}/id_ed25519"

# shellcheck source=lib/runtime.sh
source "${SCRIPT_DIR}/lib/runtime.sh"
ensure_msys2_tools
# shellcheck source=lib/config.sh
source "${SCRIPT_DIR}/lib/config.sh"
# shellcheck source=lib/templates.sh
source "${SCRIPT_DIR}/lib/templates.sh"
# shellcheck source=lib/qemu.sh
source "${SCRIPT_DIR}/lib/qemu.sh"
# shellcheck source=lib/guest.sh
source "${SCRIPT_DIR}/lib/guest.sh"
# shellcheck source=lib/alpine-image.sh
source "${SCRIPT_DIR}/lib/alpine-image.sh"
# shellcheck source=lib/vm-state.sh
source "${SCRIPT_DIR}/lib/vm-state.sh"
