[Unit]
Description=Guest Appium test server
After=network.target
[Service]
User={{USER}}
Environment=APPIUM_HOME=/opt/qemu-guests/appium/extensions
ExecStart=/opt/qemu-guests/appium/node /opt/qemu-guests/appium-run.cjs
Restart=on-failure
[Install]
WantedBy=multi-user.target
