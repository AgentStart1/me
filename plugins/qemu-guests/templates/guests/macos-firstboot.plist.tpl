<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>Label</key><string>com.me.qemu-guests.firstboot</string>
<key>ProgramArguments</key><array><string>/bin/bash</string><string>/opt/qemu-guests/macos-firstboot.sh</string></array>
<key>RunAtLoad</key><true/><key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
<key>StandardOutPath</key><string>/var/log/qemu-guests-firstboot.log</string>
<key>StandardErrorPath</key><string>/var/log/qemu-guests-firstboot.log</string>
<key>ThrottleInterval</key><integer>10</integer></dict></plist>
