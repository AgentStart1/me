#!/bin/bash
set -euo pipefail
umask 077
root=/opt/qemu-guests
session_dir=$(mktemp -d /tmp/appium-desktop.XXXXXXXX)
export XDG_RUNTIME_DIR="$session_dir/runtime" XDG_DATA_HOME="$session_dir/data"
export GNOME_KEYRING_CONTROL="$session_dir/keyring"
mkdir -p "$XDG_RUNTIME_DIR" "$XDG_DATA_HOME" "$GNOME_KEYRING_CONTROL"
owned_pids=()
cleanup() {
    for pid in "${owned_pids[@]}"; do kill "$pid" 2>/dev/null || true; done
    for pid in "${owned_pids[@]}"; do wait "$pid" 2>/dev/null || true; done
    rm -rf -- "$session_dir"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
unset XAUTHORITY AT_SPI_BUS_ADDRESS
# Leave display :0 to the console display manager, including on first boot.
Xvfb :99 -screen 0 {{WIDTH}}x{{HEIGHT}}x24 -nolisten tcp -ac >"$session_dir/xvfb.log" 2>&1 &
owned_pids+=("$!")
export DISPLAY=:99
for ((i=0;i<100;i++)); do
    kill -0 "${owned_pids[0]}"
    xdpyinfo >/dev/null 2>&1 && break
    sleep .1
done
xdpyinfo >/dev/null
openbox --sm-disable >"$session_dir/openbox.log" 2>&1 &
owned_pids+=("$!")
for ((i=0;i<100;i++)); do xprop -root _NET_SUPPORTING_WM_CHECK 2>/dev/null | grep -q 'window id' && break; sleep .1; done
xprop -root _NET_SUPPORTING_WM_CHECK | grep -q 'window id'
python3 -c 'import pyatspi; pyatspi.Registry.getDesktop(0)'
cat /proc/sys/kernel/random/uuid | gnome-keyring-daemon --unlock --foreground --components=secrets --control-directory="$GNOME_KEYRING_CONTROL" >"$session_dir/keyring.log" 2>&1 &
owned_pids+=("$!")
printf '%s\n' '{"width":{{WIDTH}},"height":{{HEIGHT}},"isolated":true}' > /opt/qemu-guests/state/desktop-ready.json
"$root/appium/node" "$root/appium-run.cjs" &
owned_pids+=("$!")
wait "${owned_pids[-1]}"
