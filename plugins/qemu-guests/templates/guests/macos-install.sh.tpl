#!/bin/sh
set -eu
target={{TARGET_DISK}}
installer={{INSTALLER_APP}}
seed=/Volumes/GUESTSEED
[ -x "$installer/Contents/Resources/startosinstall" ]
[ -f "$seed/bootstrap.pkg" ]
# The host creates this dedicated empty disk. Refuse a partitioned target rather
# than erase an interrupted install or a different attached system disk.
diskutil info "$target" | grep -Eq 'Whole:[[:space:]]+Yes'
if diskutil list "$target" | grep -Eq 'Apple_|Microsoft|Linux|EFI'; then
    echo 'Target is not empty; refusing unattended erase.' >&2
    exit 1
fi
diskutil eraseDisk APFS QemuGuest "$target"
exec "$installer/Contents/Resources/startosinstall" --agreetolicense \
    --volume /Volumes/QemuGuest --installpackage "$seed/bootstrap.pkg"
