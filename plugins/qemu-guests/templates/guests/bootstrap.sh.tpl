#!/bin/sh
set -eu
cd /opt/qemu-guests
chmod 600 backend-key
chmod 755 docker
chown {{USER}} backend-key
if [ "$(uname -s)" = Darwin ]; then
    install -m 644 docker-tunnel.plist /Library/LaunchDaemons/com.me.qemu-guests.docker-tunnel.plist
    launchctl print system/com.me.qemu-guests.docker-tunnel >/dev/null 2>&1 || launchctl bootstrap system /Library/LaunchDaemons/com.me.qemu-guests.docker-tunnel.plist
    # The unattended macOS adapter must source this file in its login shell setup.
else
    install -m 644 environment /etc/profile.d/qemu-guests.sh
    # PAM provides these settings to desktop sessions as well as login shells.
    # Preserve unrelated environment entries when replacing this plugin's keys.
    touch /etc/environment
    awk -F= 'NR==FNR {managed[$1]=1; next} !($1 in managed)' environment.pam /etc/environment > /etc/environment.qemu-guests
    cat environment.pam >> /etc/environment.qemu-guests
    chmod 644 /etc/environment.qemu-guests
    mv /etc/environment.qemu-guests /etc/environment
    install -m 644 docker-tunnel.service /etc/systemd/system/qemu-guests-docker.service
    systemctl daemon-reload
    systemctl enable --now qemu-guests-docker.service
fi
