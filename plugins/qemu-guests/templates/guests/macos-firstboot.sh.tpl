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
# An installer LaunchDaemon enables the stock SSH service before any user login.
launchctl enable system/com.openssh.sshd
launchctl load -w /System/Library/LaunchDaemons/ssh.plist 2>/dev/null || launchctl kickstart system/com.openssh.sshd
# A pre-existing SSH access group restricts PAM even after a key is accepted.
if dseditgroup -o read com.apple.access_ssh >/dev/null 2>&1; then
    dseditgroup -o edit -a '{{USER}}' -t user com.apple.access_ssh
fi
prefs='/Users/{{USER}}/Library/Preferences/com.apple.SetupAssistant'
install -d -m 700 -o '{{USER}}' -g staff '/Users/{{USER}}/Library/Preferences'
for flag in DidSeeAccessibility DidSeeAppearanceSetup DidSeeCloudSetup DidSeePrivacy DidSeeScreenTime DidSeeSiriSetup DidSeeSyncSetup DidSeeTouchIDSetup DidSeeTrueToneSetup RunNonInteractive; do
    defaults write "$prefs" "$flag" -bool YES
done
defaults write "$prefs" LastSeenCloudProductVersion -string "$(sw_vers -productVersion)"
defaults write "$prefs" LastSeenBuddyBuildVersion -string "$(sw_vers -buildVersion)"
chown '{{USER}}:staff' "$prefs.plist"
# The standard QEMU USB keyboard is ANSI (product 1, vendor 1575, country 0).
# Preserve any other keyboard mappings supplied by an operator.
defaults write /Library/Preferences/com.apple.keyboardtype keyboardtype -dict-add '1-1575-0' -int 40
bash bootstrap.sh
/usr/bin/fdesetup status | grep -Fx 'FileVault is Off.' >/dev/null
./appium/node macos-autologin.cjs '{{USER}}'
[ -s /etc/kcpassword ]
[ "$(defaults read /Library/Preferences/com.apple.loginwindow autoLoginUser)" = '{{USER}}' ]
/usr/bin/pmset -a sleep 0 displaysleep 0
touch /var/db/.AppleSetupDone /var/db/qemu-guests-ready
rm -f account-password
/sbin/shutdown -r now
