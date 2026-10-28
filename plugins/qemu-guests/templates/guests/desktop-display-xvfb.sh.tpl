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
