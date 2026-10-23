#!/usr/bin/env bash
set -euo pipefail
export PATH="/ucrt64/bin:/usr/bin:$PATH"
source_dir="$(cygpath -u "$1")"
build_dir="$(cygpath -u "$2")"
jobs="$3"
shift 3
pacman -S --needed --noconfirm mingw-w64-ucrt-x86_64-gcc \
  mingw-w64-ucrt-x86_64-meson mingw-w64-ucrt-x86_64-ninja \
  mingw-w64-ucrt-x86_64-pkgconf mingw-w64-ucrt-x86_64-glib2 \
  mingw-w64-ucrt-x86_64-pixman mingw-w64-ucrt-x86_64-libslirp diffutils patch
for patch_file in "$@"; do
  patch --fuzz=0 -d "$source_dir" -p1 < "$(cygpath -u "$patch_file")"
done
mkdir "$build_dir"
cd "$build_dir"
"$source_dir/configure" --target-list=x86_64-softmmu --enable-whpx \
  --disable-tcg --disable-docs --disable-tools --disable-guest-agent \
  --disable-werror --disable-sdl --disable-gtk --disable-vnc --disable-spice \
  --disable-curl --enable-slirp --python=/ucrt64/bin/python.exe
ninja -j"$jobs" qemu-system-x86_64.exe
