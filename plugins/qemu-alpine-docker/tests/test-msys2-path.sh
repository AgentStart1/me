#!/bin/bash
# Windows runtime regression; no VM, network, or credentials required.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../scripts/lib/runtime.sh"
if ! is_windows; then
    echo 'SKIP: requires Git Bash or MSYS2 on Windows'
    exit 0
fi
unset QEMU_ALPINE_SKIP_MSYS2_PATH
original_path="$PATH"
commands=(bash env ssh ssh-keygen tar curl)
original_commands=()
for cmd in "${commands[@]}"; do
    original_commands+=("$(command -v "$cmd" || true)")
done
ensure_msys2_tools
[[ "$PATH" == "$original_path" || "$PATH" == "$original_path:"* ]]
for index in "${!commands[@]}"; do
    if [ -n "${original_commands[$index]}" ]; then
        [ "$(command -v "${commands[$index]}")" = "${original_commands[$index]}" ]
    fi
done
extended_path="$PATH"
ensure_msys2_tools
[ "$PATH" = "$extended_path" ]
QEMU_DOCKER_SSH_PORT=probe QEMU_DOCKER_SSH_KEY=probe bash -c \
    '[ "${QEMU_DOCKER_SSH_PORT:-}" = probe ] && [ "${QEMU_DOCKER_SSH_KEY:-}" = probe ]'
echo 'PASS: fallback paths preserve command choices and child Bash environment; initialization is idempotent'
for cmd in qemu-system-x86_64 qemu-img xorriso; do
    if command -v "$cmd" >/dev/null; then
        "$cmd" --version
    fi
done
