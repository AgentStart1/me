#!/usr/bin/env bash
set -euo pipefail
export PATH="/ucrt64/bin:/usr/bin:$PATH"
export PYTHONUTF8=1
work="$(cygpath -u "$1")"
export PKG_CONFIG_PATH="$work/package/lib/pkgconfig"
mkdir "$work/qemu-build"
cd "$work/qemu-build"
"$work/reims-vgpu/vendor/qemu/configure" --target-list=x86_64-softmmu \
    --enable-whpx --disable-tcg --enable-pvg --enable-slirp \
    --disable-docs --disable-tools --disable-guest-agent --disable-sdl \
    --disable-gtk --disable-vnc --disable-spice --python=/ucrt64/bin/python.exe
ninja -j"$2" qemu-system-x86_64.exe
