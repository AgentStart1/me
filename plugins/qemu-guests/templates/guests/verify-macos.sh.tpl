#!/bin/bash
set -euo pipefail
[ -f /var/db/qemu-guests-ready ]
[ "$(stat -f %Su /dev/console)" = '{{USER}}' ]
launchctl print "gui/$(id -u)/com.me.qemu-guests.appium" >/dev/null
/usr/bin/curl --noproxy 127.0.0.1 -fsS http://127.0.0.1:4723/status | /opt/qemu-guests/appium/node -e 'let s="";process.stdin.on("data",v=>s+=v);process.stdin.on("end",()=>{if(!JSON.parse(s).value.ready)process.exit(1)})'
