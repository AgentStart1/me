#!/bin/bash
set -euo pipefail
# Boot-time package installation happens after launchd's initial directory scan.
# Start the new service on the running target, never on the preparation/Recovery OS.
if [ "$3" = / ]; then
    launchctl bootstrap system /Library/LaunchDaemons/com.me.qemu-guests.firstboot.plist ||
        launchctl kickstart system/com.me.qemu-guests.firstboot
fi
