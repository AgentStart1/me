#!/bin/bash
set -euo pipefail
# Boot-time package installation happens after launchd's initial directory scan.
# Start the new service on the running target, never on the preparation/Recovery OS.
if [ "$3" = / ]; then
    # Explicitly installing this private package also rearms bootstrap for an
    # OS upgrade. Its payload supplies the reviewed existing-account credential.
    rm -f /var/db/qemu-guests-ready
    launchctl bootstrap system /Library/LaunchDaemons/com.me.qemu-guests.firstboot.plist ||
        launchctl kickstart system/com.me.qemu-guests.firstboot
fi
