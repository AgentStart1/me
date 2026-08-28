#!/bin/bash
# Build an unattended Alpine system disk, verify Docker, and mark it ready.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=vm-utils.sh
source "${SCRIPT_DIR}/vm-utils.sh"

PROFILE_ARG="${1:-${PLUGIN_DIR}/profiles/dev.profile}"
load_profile "$PROFILE_ARG"

for key in VM_NAME VM_MEMORY VM_CPUS VM_DISK_SIZE SSH_PORT DOCKER_DAEMON_PORT TESTCONTAINERS_PORT_START TESTCONTAINERS_PORT_END; do
    require_profile_value "$key"
done
[[ "$VM_NAME" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]] || {
    echo "Error: VM_NAME contains unsupported characters." >&2
    exit 1
}

ALPINE_BRANCH="${ALPINE_BRANCH:-v3.24}"
ALPINE_MIRROR_BASE="${ALPINE_MIRROR_BASE:-auto}"
ALPINE_FALLBACK_MIRROR="https://dl-cdn.alpinelinux.org/alpine"
TEMPLATE_DIR="${PLUGIN_DIR}/templates"
INSTALL_TIMEOUT="${INSTALL_TIMEOUT:-1800}"
BOOT_TIMEOUT="${BOOT_TIMEOUT:-300}"
PRELOAD_IMAGES="${PRELOAD_IMAGES:-}"
VERIFY_EXISTING="${VERIFY_EXISTING:-false}"
VERIFY_ONLY=false

VM_HOME="${VM_DIR}/${VM_NAME}"
VM_DISK="${VM_HOME}/disk.qcow2"
MODIFIED_ISO="${VM_HOME}/alpine-auto.iso"
OVERLAY_DIR="${VM_HOME}/overlay"
OVERLAY_ARCHIVE="${VM_HOME}/localhost.apkovl.tar.gz"
KERNEL_IMAGE="${VM_HOME}/vmlinuz-virt"
INITRAMFS_IMAGE="${VM_HOME}/initramfs-virt"
INSTALL_LOG="${VM_HOME}/install-console.log"
BOOT_LOG="${VM_HOME}/verify-console.log"
VM_DISK_NATIVE="$(qemu_native_path "$VM_DISK")"
MODIFIED_ISO_NATIVE="$(qemu_native_path "$MODIFIED_ISO")"
INSTALL_LOG_NATIVE="$(qemu_native_path "$INSTALL_LOG")"
BOOT_LOG_NATIVE="$(qemu_native_path "$BOOT_LOG")"
KERNEL_IMAGE_NATIVE="$(qemu_native_path "$KERNEL_IMAGE")"
INITRAMFS_IMAGE_NATIVE="$(qemu_native_path "$INITRAMFS_IMAGE")"
READY_FILE="$(vm_ready_file)"

if [ -f "$VM_DISK" ]; then
    if [ -f "$READY_FILE" ]; then
        echo "VM '${VM_NAME}' is already provisioned; preserving its Docker image cache." >&2
        exit 0
    fi
    if [ "$VERIFY_EXISTING" = "true" ]; then
        VERIFY_ONLY=true
        echo "Resuming verification for existing disk ${VM_DISK}." >&2
    else
        echo "Error: ${VM_DISK} exists without a ready marker." >&2
        echo "Inspect ${INSTALL_LOG}; set VERIFY_EXISTING=true only when the installation is known to be complete." >&2
        exit 1
    fi
fi

QEMU_BIN="$(resolve_qemu)"
QEMU_IMG_BIN="$(resolve_qemu_img "$QEMU_BIN")"
configure_qemu_acceleration "$QEMU_BIN"
require_command xorriso
require_command tar
require_command curl
ensure_ssh_key
VM_ISO="$(ensure_alpine_image)"
build_netdev_value >/dev/null
acquire_single_vm_lock

QEMU_PID=""
COMPLETED=false
cleanup_create() {
    if [ "$COMPLETED" != "true" ]; then
        if process_is_running "${QEMU_PID:-}"; then
            kill "$QEMU_PID" 2>/dev/null || true
            wait_for_process_exit "$QEMU_PID" 10 || kill -9 "$QEMU_PID" 2>/dev/null || true
        fi
        clear_vm_process_state
    fi
}
trap cleanup_create EXIT INT TERM

if [ "$VERIFY_ONLY" != "true" ]; then
mkdir -p "$VM_HOME" "${OVERLAY_DIR}/etc/local.d" "${OVERLAY_DIR}/etc/runlevels/default"
mkdir -p "${OVERLAY_DIR}/etc/sysctl.d" "${OVERLAY_DIR}/etc/unbound"
mkdir -p "${OVERLAY_DIR}/usr/local/libexec"

cp "${SSH_KEY}.pub" "${OVERLAY_DIR}/root-key.pub"
cp "${SCRIPT_DIR}/select-apk-mirror.sh" "${OVERLAY_DIR}/usr/local/libexec/select-apk-mirror"
chmod +x "${OVERLAY_DIR}/usr/local/libexec/select-apk-mirror"
printf '%s\n%s\n' "$ALPINE_BRANCH" "$ALPINE_MIRROR_BASE" > "${OVERLAY_DIR}/mirror-config"
ROOT_SSH_KEY="$(tr -d '\r\n' < "${SSH_KEY}.pub")"
render_template "${TEMPLATE_DIR}/setup-alpine.answers.tpl" "${OVERLAY_DIR}/answers" \
    VM_NAME "$VM_NAME" \
    FALLBACK_MAIN "${ALPINE_FALLBACK_MIRROR}/${ALPINE_BRANCH}/main" \
    FALLBACK_COMMUNITY "${ALPINE_FALLBACK_MIRROR}/${ALPINE_BRANCH}/community" \
    ROOT_SSH_KEY "$ROOT_SSH_KEY"
render_template "${TEMPLATE_DIR}/testcontainers-ports.conf.tpl" \
    "${OVERLAY_DIR}/etc/sysctl.d/99-testcontainers-ports.conf" \
    TESTCONTAINERS_PORT_START "$TESTCONTAINERS_PORT_START" \
    TESTCONTAINERS_PORT_END "$TESTCONTAINERS_PORT_END"
render_template "${TEMPLATE_DIR}/docker-daemon.json.tpl" \
    "${OVERLAY_DIR}/docker-daemon.json" \
    DOCKER_GUEST_PORT "2375" \
    DOCKER_DNS_ADDRESS "172.17.0.1"
render_template "${TEMPLATE_DIR}/unbound.conf.tpl" \
    "${OVERLAY_DIR}/etc/unbound/unbound.conf" \
    DNS_LISTEN_ADDRESS "0.0.0.0" \
    LOCAL_DNS_NETWORK "127.0.0.1/32" \
    DOCKER_DNS_NETWORK "172.17.0.0/16" \
    LOCAL_DNS_PORT "53" \
    QEMU_DNS_ADDRESS "10.0.2.3" \
    QEMU_DNS_PORT "53"
render_template "${TEMPLATE_DIR}/use-local-dns.start.tpl" \
    "${OVERLAY_DIR}/etc/local.d/use-local-dns.start" \
    LOCAL_DNS_ADDRESS "127.0.0.1"
render_template "${TEMPLATE_DIR}/udhcpc.conf.tpl" \
    "${OVERLAY_DIR}/udhcpc.conf" \
    RESOLV_CONF_MODE "no"
render_template "${TEMPLATE_DIR}/setup.start.tpl" \
    "${OVERLAY_DIR}/etc/local.d/setup.start" \
    ALPINE_FALLBACK_MIRROR "$ALPINE_FALLBACK_MIRROR"
chmod +x "${OVERLAY_DIR}/etc/local.d/setup.start"
chmod +x "${OVERLAY_DIR}/etc/local.d/use-local-dns.start"

# OpenRC identifies services by the entries in the runlevel directory.
touch "${OVERLAY_DIR}/etc/runlevels/default/local"

rm -f "${OVERLAY_DIR}/localhost.apkovl.tar.gz"
(cd "$OVERLAY_DIR" && tar --owner=0 --group=0 -czf "$OVERLAY_ARCHIVE" .)

echo "Creating unattended Alpine ISO..." >&2
rm -f "$MODIFIED_ISO"
xorriso -indev "$VM_ISO" -outdev "$MODIFIED_ISO_NATIVE" \
    -map "$OVERLAY_ARCHIVE" /localhost.apkovl.tar.gz \
    -boot_image any replay >/dev/null

rm -f "$KERNEL_IMAGE" "$INITRAMFS_IMAGE"
xorriso -osirrox on -indev "$MODIFIED_ISO_NATIVE" \
    -extract /boot/vmlinuz-virt "$KERNEL_IMAGE" \
    -extract /boot/initramfs-virt "$INITRAMFS_IMAGE" >/dev/null

echo "Creating persistent disk ${VM_DISK} (${VM_DISK_SIZE})..." >&2
"$QEMU_IMG_BIN" create -f qcow2 "$VM_DISK_NATIVE" "$VM_DISK_SIZE"

install_args=(
    -name "${VM_NAME}-install"
    "${QEMU_ACCEL_ARGS[@]}"
    -m "$VM_MEMORY"
    -smp "$VM_CPUS"
    -drive "file=${VM_DISK_NATIVE},format=qcow2,if=virtio"
    -cdrom "$MODIFIED_ISO_NATIVE"
    -kernel "$KERNEL_IMAGE_NATIVE"
    -initrd "$INITRAMFS_IMAGE_NATIVE"
    -append "modules=loop,squashfs,sd-mod,usb-storage,virtio_net,af_packet,ext4,fat,vfat modloop=/media/sr0/boot/modloop-virt console=ttyS0,115200"
    -display none
    -serial "file:${INSTALL_LOG_NATIVE}"
    -monitor none
    -netdev user,id=net0
    -device virtio-net-pci,netdev=net0
)

echo "Installing Alpine and Docker with ${QEMU_ACCELERATOR} acceleration (timeout: ${INSTALL_TIMEOUT}s)..." >&2
"$QEMU_BIN" "${install_args[@]}" &
QEMU_PID=$!
register_vm_process "$QEMU_PID"
if ! wait_for_process_exit "$QEMU_PID" "$INSTALL_TIMEOUT"; then
    echo "Error: unattended installation timed out; see ${INSTALL_LOG}." >&2
    exit 1
fi
if ! wait "$QEMU_PID"; then
    echo "Error: installer QEMU exited unsuccessfully; see ${INSTALL_LOG}." >&2
    exit 1
fi
ACTUAL_DISK_SIZE="$("$QEMU_IMG_BIN" info --output=json "$VM_DISK_NATIVE" | sed -n 's/.*"actual-size":[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -n 1)"
if [ -z "$ACTUAL_DISK_SIZE" ] || [ "$ACTUAL_DISK_SIZE" -lt 1048576 ]; then
    echo "Error: installer powered off without writing an Alpine system to disk; see ${INSTALL_LOG}." >&2
    exit 1
fi
clear_vm_process_state
acquire_single_vm_lock
fi

NETDEV_VALUE="$(build_netdev_value)"
verify_args=(
    -name "${VM_NAME}-verify"
    "${QEMU_ACCEL_ARGS[@]}"
    -m "$VM_MEMORY"
    -smp "$VM_CPUS"
    -drive "file=${VM_DISK_NATIVE},format=qcow2,if=virtio"
    -display none
    -serial "file:${BOOT_LOG_NATIVE}"
    -monitor none
    -netdev "$NETDEV_VALUE"
    -device virtio-net-pci,netdev=net0
)

echo "Booting the installed disk for verification..." >&2
"$QEMU_BIN" "${verify_args[@]}" &
QEMU_PID=$!
register_vm_process "$QEMU_PID"
wait_for_ssh "$BOOT_TIMEOUT" "$QEMU_PID"
ssh_exec "test -f /etc/qemu-alpine-docker-image && test -s /etc/qemu-alpine-docker-mirror && grep -q '/${ALPINE_BRANCH}/main' /etc/apk/repositories && grep -qx 'RESOLV_CONF=\"no\"' /etc/udhcpc/udhcpc.conf && rc-service docker status >/dev/null && rc-service unbound status >/dev/null && grep -qx 'nameserver 127.0.0.1' /etc/resolv.conf && nslookup dl-cdn.alpinelinux.org 127.0.0.1 >/dev/null"
wait_for_docker_api 120
ssh_exec "docker info >/dev/null"
ssh_exec "set -- \$(sysctl -n net.ipv4.ip_local_port_range); test \"\$1\" = '${TESTCONTAINERS_PORT_START}' && test \"\$2\" = '${TESTCONTAINERS_PORT_END}'"

if [ -n "$PRELOAD_IMAGES" ]; then
    IFS=',' read -ra preload_list <<< "$PRELOAD_IMAGES"
    for image in "${preload_list[@]}"; do
        validate_image_reference "$image"
        ssh_exec "docker image inspect '${image}' >/dev/null 2>&1 || docker pull '${image}'"
    done
fi

ssh_exec "poweroff" >/dev/null 2>&1 || true
if ! wait_for_process_exit "$QEMU_PID" 90; then
    echo "Warning: guest did not power off; stopping QEMU after successful verification." >&2
    kill "$QEMU_PID" 2>/dev/null || true
    wait_for_process_exit "$QEMU_PID" 10 || kill -9 "$QEMU_PID" 2>/dev/null || true
fi
wait "$QEMU_PID" 2>/dev/null || true
clear_vm_process_state

printf 'verified=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$READY_FILE"
COMPLETED=true
trap - EXIT INT TERM

echo "VM '${VM_NAME}' is ready." >&2
echo "Persistent Docker cache: ${VM_DISK}" >&2
echo "Start it with: ./scripts/start-vm.sh ${PROFILE_ARG}" >&2
