#!/bin/sh
set -eu
umask 077
mount_dir=$(mktemp -d /run/appium-seed.XXXXXXXX)
cleanup() {
    umount "$mount_dir" 2>/dev/null || true
    rmdir "$mount_dir" 2>/dev/null || true
}
trap cleanup EXIT
mount -o ro /dev/disk/by-label/cidata "$mount_dir"
python3 -m zipfile -e "$mount_dir/payload.zip" /opt/qemu-guests
cleanup
trap - EXIT
exec /bin/bash /opt/qemu-guests/bootstrap.sh
