# LightDM owns Xorg and XFCE. Keep its DISPLAY and XAUTHORITY for GPU access.
unset AT_SPI_BUS_ADDRESS
outputs=$(xrandr --query | awk '$2 == "connected" {print $1}')
test "$(printf '%s\n' "$outputs" | wc -l)" -eq 1
xrandr --output "$outputs" --mode {{WIDTH}}x{{HEIGHT}}
xset s off
xset -dpms
python3 "$root/verify-gpu.py" --publish
