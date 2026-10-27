#!/usr/bin/env bash
set -euo pipefail
export PATH="/ucrt64/bin:/usr/bin:$PATH"
work="$(cygpath -u "$1")"
jobs="$2"
pacman -S --needed --noconfirm mingw-w64-ucrt-x86_64-gcc \
  mingw-w64-ucrt-x86_64-meson mingw-w64-ucrt-x86_64-ninja \
  mingw-w64-ucrt-x86_64-pkgconf mingw-w64-ucrt-x86_64-glib2 \
  mingw-w64-ucrt-x86_64-pixman mingw-w64-ucrt-x86_64-libslirp \
  mingw-w64-ucrt-x86_64-libepoxy mingw-w64-ucrt-x86_64-SDL2 diffutils patch
for name in qemu-whpx-reset qemu-whpx-cet qemu-virgl qemu-gl-snapshot; do
  patch --fuzz=0 -d "$work/qemu-11.1.2" -p1 < "$work/inputs/$name.patch"
done
patch --fuzz=0 -d "$work/virglrenderer-1.3.0" -p1 < "$work/inputs/virglrenderer.patch"
prefix="$work/prefix"
meson setup "$work/virgl-build" "$work/virglrenderer-1.3.0" \
  --prefix "$(cygpath -m "$prefix")" --buildtype=release --wrap-mode=nodownload
meson compile -C "$work/virgl-build" -j "$jobs"
meson install -C "$work/virgl-build"
export PKG_CONFIG_PATH="$(cygpath -m "$prefix/lib/pkgconfig")"
export PATH="$prefix/bin:$PATH"
mkdir "$work/qemu-build"
cd "$work/qemu-build"
"$work/qemu-11.1.2/configure" --target-list=x86_64-softmmu --enable-whpx \
  --disable-tcg --disable-docs --disable-tools --disable-guest-agent \
  --disable-werror --enable-sdl --enable-opengl --enable-virglrenderer \
  --disable-gtk --disable-vnc --disable-spice --disable-curl --enable-slirp \
  --python=/ucrt64/bin/python.exe
ninja -j"$jobs" qemu-system-x86_64.exe
