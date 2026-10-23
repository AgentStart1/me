#!/bin/sh
set -eu
target={{TARGET_DISK}}
installer={{INSTALLER_APP}}
seed=/Volumes/GUESTSEED
[ -x "$installer/Contents/Resources/startosinstall" ] || {
    echo "Prepared installer application is missing startosinstall: $installer" >&2
    exit 1
}
[ -f "$seed/bootstrap.pkg" ] || { echo 'Bootstrap product package is missing.' >&2; exit 1; }
case "$target" in
    serial:*)
        serial=${target#serial:}
        target=$(/usr/sbin/ioreg -r -c IOBlockStorageDevice -l -w0 |
            /usr/bin/awk -v serial="$serial" -f "$seed/macos-target-disk.awk") || {
            echo 'Expected one whole disk matching the configured target serial; refusing erase.' >&2
            exit 1
        }
        ;;
esac
# The host creates this dedicated empty disk. Refuse a partitioned target rather
# than erase an interrupted install or a different attached system disk.
diskutil info "$target" | grep -Eq 'Whole:[[:space:]]+Yes'
if diskutil list "$target" | grep -Eq 'Apple_|Microsoft|Linux|EFI'; then
    echo 'Target is not empty; refusing unattended erase.' >&2
    exit 1
fi
diskutil eraseDisk APFS QemuGuest "$target"
exec "$installer/Contents/Resources/startosinstall" --agreetolicense \
    --volume /Volumes/QemuGuest --installpackage "$seed/bootstrap.pkg" --nointeraction
