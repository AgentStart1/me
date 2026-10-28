#!/bin/sh
set -eu
export TEST_DESKTOP_USER='{{USER}}'
cd /opt/qemu-guests
if [ "$(uname -s)" = Darwin ]; then
    ditto -xk appium-runtime.zip appium
else
    python3 -m zipfile -e appium-runtime.zip appium
fi
chmod 755 appium/node
./appium/node relocate-runtime.cjs
if [ -f setup-hooks.json ]; then
    ./appium/node run-setup-hooks.cjs
fi
chown -R {{USER}} appium
chmod 644 appium-run.cjs
if [ "$(uname -s)" = Darwin ]; then
    chmod 644 appium-run.cjs
    install -d -o {{USER}} /Users/{{USER}}/Library/LaunchAgents
    install -m 644 -o {{USER}} appium.plist /Users/{{USER}}/Library/LaunchAgents/com.me.qemu-guests.appium.plist
else
    install -m 644 appium.service /etc/systemd/system/qemu-guests-appium.service
    if [ -f desktop.json ]; then
        install -d -o {{USER}} -m 700 /opt/qemu-guests/state
        install -d /etc/systemd/system/qemu-guests-appium.service.d
        printf '%s\n' '[Service]' 'ExecStart=' 'ExecStart=/usr/bin/dbus-run-session -- /bin/bash /opt/qemu-guests/desktop-session.sh' > /etc/systemd/system/qemu-guests-appium.service.d/desktop.conf
        chmod 644 desktop-session.sh desktop.json
    fi
    systemctl daemon-reload
    if [ -f graphics.json ]; then
        chmod 644 verify-gpu.py
        account_home=$(getent passwd '{{USER}}' | cut -d: -f6)
        test -n "$account_home"
        install -d -m 700 -o {{USER}} "$account_home/.config" "$account_home/.config/autostart"
        install -m 644 -o {{USER}} desktop-autostart.desktop "$account_home/.config/autostart/qemu-guests-appium.desktop"
        # The graphical login owns the GPU session; do not launch a competing Xvfb service.
        systemctl disable --now qemu-guests-appium.service
    else
        systemctl enable --now qemu-guests-appium.service
    fi
fi
