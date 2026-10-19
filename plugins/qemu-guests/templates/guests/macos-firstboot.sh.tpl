#!/bin/bash
set -euo pipefail
[ ! -f /var/db/qemu-guests-ready ] || exit 0
cd /opt/qemu-guests
if ! id '{{USER}}' >/dev/null 2>&1; then
    /usr/sbin/sysadminctl -addUser '{{USER}}' -fullName Developer -admin \
        -password "$(cat account-password)" >/dev/null 2>&1
fi
install -d -m 700 -o '{{USER}}' -g staff '/Users/{{USER}}'
install -d -m 700 -o '{{USER}}' -g staff '/Users/{{USER}}/.ssh'
install -m 600 -o '{{USER}}' -g staff access.pub '/Users/{{USER}}/.ssh/authorized_keys'
chmod 644 environment
for profile in /etc/zshenv /etc/profile; do
    grep -qF '. /opt/qemu-guests/environment' "$profile" 2>/dev/null || echo '. /opt/qemu-guests/environment' >> "$profile"
done
# An installer LaunchDaemon enables the stock SSH service before any user login.
launchctl enable system/com.openssh.sshd
launchctl load -w /System/Library/LaunchDaemons/ssh.plist 2>/dev/null || launchctl kickstart system/com.openssh.sshd
bash bootstrap.sh
touch /var/db/.AppleSetupDone /var/db/qemu-guests-ready
rm -f account-password
/sbin/shutdown -r now
