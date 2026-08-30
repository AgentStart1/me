#!/bin/bash
# setup.sh — Download Alpine image and verify prerequisites for QEMU Alpine Docker.
#
# This script checks that all required tools are available and downloads the
# Alpine ISO image if it doesn't already exist. It's intended to be run once
# before creating the first VM.
#
# Required tools:
#   - qemu-system-x86_64 (QEMU emulator)
#   - qemu-img (disk image tool)
#   - ssh, ssh-keygen (OpenSSH client)
#   - xorriso (ISO manipulation)
#   - tar (archive creation)
#   - curl (download)
#
# Directories created:
#   - $IMAGES_DIR (downloaded Alpine ISOs)
#   - $VM_DIR (per-VM directories)
#   - $RUN_DIR (runtime state)
#
# The script also generates an SSH key pair if one doesn't exist.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=vm-utils.sh
source "${SCRIPT_DIR}/vm-utils.sh"

echo "=== QEMU Alpine Docker Setup ===" >&2

echo "Checking QEMU..." >&2
QEMU_BIN="$(resolve_qemu)"
echo "QEMU found: ${QEMU_BIN}" >&2
QEMU_IMG_BIN="$(resolve_qemu_img "$QEMU_BIN")"
echo "qemu-img found: ${QEMU_IMG_BIN}" >&2

echo "Checking SSH client..." >&2
require_command ssh "OpenSSH client"
require_command ssh-keygen "OpenSSH key generator"
require_command xorriso "xorriso ISO editor"
require_command tar
require_command curl
echo "SSH client found." >&2

# Create directories
mkdir -p "${IMAGES_DIR}" "${VM_DIR}" "${RUN_DIR}"

# Ensure SSH key exists
echo "Checking SSH key..." >&2
ensure_ssh_key

# Download Alpine image
echo "Checking Alpine image..." >&2
ALPINE_IMAGE_PATH="$(ensure_alpine_image)"
echo "Alpine image ready: ${ALPINE_IMAGE_PATH}" >&2

echo "" >&2
echo "=== Setup complete ===" >&2
echo "Images directory: ${IMAGES_DIR}" >&2
echo "VM directory: ${VM_DIR}" >&2
echo "SSH key: ${SSH_KEY}" >&2
