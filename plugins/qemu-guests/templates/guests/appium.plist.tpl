<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>Label</key><string>com.me.qemu-guests.appium</string>
<key>ProgramArguments</key><array><string>/opt/qemu-guests/appium/node</string><string>/opt/qemu-guests/appium-run.cjs</string></array>
<key>EnvironmentVariables</key><dict><key>APPIUM_HOME</key><string>/opt/qemu-guests/appium/extensions</string></dict>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
<key>StandardOutPath</key><string>/opt/qemu-guests/appium/appium.log</string><key>StandardErrorPath</key><string>/opt/qemu-guests/appium/appium-error.log</string>
</dict></plist>
