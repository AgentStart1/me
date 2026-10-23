#!/bin/bash
# Build dedicated boot media on a macOS preparation machine.
set -euo pipefail
[ "$(uname -s)" = Darwin ] || { echo 'Apple createinstallmedia and hdiutil are required.' >&2; exit 1; }
[ $# -ge 2 ] && [ $# -le 3 ] || { echo 'Usage: create-macos-media.sh /path/Install-macOS.app /absolute/output.iso [24g]' >&2; exit 2; }
installer="$1"; output="$2"; size="${3:-24g}"
[[ "$output" = /* ]] && [[ "$size" =~ ^[1-9][0-9]*g$ ]] || { echo 'Use an absolute output path and positive size in g.' >&2; exit 2; }
[ -x "$installer/Contents/Resources/createinstallmedia" ]
[ ! -e "$output" ] || { echo 'Output already exists; refusing replacement.' >&2; exit 1; }
staging="$(mktemp -d)"; device=""; uncertain=false
cleanup() {
    if [ "$uncertain" = true ]; then
        echo "Image attachment is uncertain; retain $staging for inspection." >&2
        return
    fi
    [ -z "$device" ] || hdiutil detach "$device" >/dev/null
    rm -rf -- "$staging"
}
trap cleanup EXIT
# Keep preparation storage proportional to installer content, rather than
# allocating both a full raw staging image and the final ISO at once.
hdiutil create -o "$staging/install.sparseimage" -type SPARSE -size "$size" -layout GPTSPUD -fs 'HFS+J' >/dev/null
mkdir "$staging/mount"
uncertain=true
hdiutil attach "$staging/install.sparseimage" -noverify -mountpoint "$staging/mount" > "$staging/attach.txt"
device="$(awk '/^\/dev\/disk/{print $1; exit}' "$staging/attach.txt")"
[[ "$device" =~ ^/dev/disk[0-9]+$ ]] || { echo 'Could not identify the newly attached image.' >&2; exit 1; }
uncertain=false
sudo "$installer/Contents/Resources/createinstallmedia" --nointeraction --volume "$staging/mount"
hdiutil detach "$device" >/dev/null; device=""
hdiutil convert "$staging/install.sparseimage" -format UDTO -o "$staging/output" >/dev/null
if ! ln "$staging/output.cdr" "$output" 2>/dev/null; then
    # A different destination filesystem needs a copy; never replace an output.
    set -o noclobber
    cat "$staging/output.cdr" > "$output"
fi
echo 'Bootable macOS installer media created. Configure matching QEMU firmware and boot hardware separately.'
