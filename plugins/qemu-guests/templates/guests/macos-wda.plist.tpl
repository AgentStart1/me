<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>{{LABEL}}</string>
<key>ProgramArguments</key><array>
<string>/usr/bin/xcodebuild</string><string>test-without-building</string>
<string>-xctestrun</string><string>{{XCTESTRUN}}</string>
<string>-destination</string><string>platform=macOS,arch=x86_64</string>
<string>-disableAutomaticPackageResolution</string>
</array>
<key>EnvironmentVariables</key><dict>
<key>USE_PORT</key><string>{{PORT}}</string><key>USE_HOST</key><string>127.0.0.1</string>
</dict>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
<key>StandardOutPath</key><string>{{LOG_DIRECTORY}}/wda.log</string>
<key>StandardErrorPath</key><string>{{LOG_DIRECTORY}}/wda-error.log</string>
</dict></plist>
