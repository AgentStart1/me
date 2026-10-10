#!/usr/bin/env bash
# Run inside the runtime image; no Alpine download or guest provisioning needed.
set -euo pipefail
PLUGIN_DIR="${QEMU_PLUGIN_DIR:-/opt/qemu-alpine-docker}"
source "$PLUGIN_DIR/scripts/vm-utils.sh"
load_profile "$PLUGIN_DIR/profiles/dev.profile"
[[ "$(id -u)" != 0 ]]
[[ ! -e /var/run/docker.sock ]]
[[ "$(awk '/^CapEff:/ {print $2}' /proc/self/status)" == 0000000000000000 ]]
QEMU_BIN="$(resolve_qemu)"
configure_qemu_acceleration "$QEMU_BIN"
# This smoke test deliberately runs without /dev/kvm.
[[ "$QEMU_ACCELERATOR" == tcg ]]
mkdir -p "$VM_DIR"
"$QEMU_BIN" -name "$VM_NAME" "${QEMU_ACCEL_ARGS[@]}" \
    -machine q35 -m 64 -smp 1 -nodefaults -display none -S \
    -netdev user,id=net0,hostfwd=tcp:127.0.0.1:2222-:22,hostfwd=tcp:127.0.0.1:2375-:2375 \
    -device virtio-net-pci,netdev=net0 &
qemu_test_pid=$!
trap 'kill "$qemu_test_pid" 2>/dev/null || true; wait "$qemu_test_pid" 2>/dev/null || true' EXIT
printf '%s\n' "$qemu_test_pid" > "$(vm_pid_file)"
sleep 1
kill -0 "$qemu_test_pid"
python3 "$PLUGIN_DIR/scripts/status.py" | python3 -c '
import json,sys
snapshot=json.load(sys.stdin)
assert snapshot["vm"]["state"] == "running", snapshot
assert snapshot["vm"]["accelerator"] == "tcg", snapshot
assert snapshot["services"]["docker"]["state"] != "healthy", snapshot
assert snapshot["containers"]["state"] == "unavailable", snapshot
print("PASS: unprivileged non-root TCG QEMU with user networking and live process status; no guest OS was provisioned")
'
VM_ACCELERATOR=kvm
if configure_qemu_acceleration "$QEMU_BIN"; then
    echo 'FAIL: Explicit KVM unexpectedly succeeded without /dev/kvm' >&2
    exit 1
fi
echo 'PASS: explicit KVM reports unavailable device instead of silently falling back'
