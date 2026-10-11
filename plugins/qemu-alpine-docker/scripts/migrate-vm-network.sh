#!/bin/bash
# Explicit migration preserves the disk, images and matching Docker publish pool.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/vm-utils.sh"
PROFILE_ARG="${1:-${PLUGIN_DIR}/profiles/dev.profile}"
load_profile "$PROFILE_ARG"
begin_vm_operation
require_known_vm_process
vm_is_running || { echo 'Error: migration requires the existing guest running with SSH access.' >&2; exit 1; }
build_forward_mappings >/dev/null
install_gvproxy
ssh_exec "sh -s" < "${PLUGIN_DIR}/templates/migrate-gvproxy.sh.tpl"
export VM_OPERATION_ALLOW_NESTED=migration
"${SCRIPT_DIR}/stop-vm.sh" "$PROFILE_ARG"
"${SCRIPT_DIR}/start-vm.sh" "$PROFILE_ARG"
