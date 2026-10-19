#!/bin/bash
# Run on a macOS preparation machine; never modifies the host OS installation.
set -euo pipefail
[ "$(uname -s)" = Darwin ] || { echo 'macOS pkgbuild/productbuild are required.' >&2; exit 1; }
[ $# -eq 2 ] || { echo 'Usage: build-macos-bootstrap.sh payload.zip /absolute/path/bootstrap.pkg' >&2; exit 2; }
payload="$1"; output="$2"
[[ "$output" = /* ]] || { echo 'Output must be an absolute path.' >&2; exit 2; }
[ ! -e "$output" ] || { echo 'Output already exists; refusing replacement.' >&2; exit 1; }
staging="$(mktemp -d)"
trap 'rm -rf -- "$staging"' EXIT
mkdir -p "$staging/root/opt/qemu-guests" "$staging/root/Library/LaunchDaemons"
chmod 755 "$staging/root" "$staging/root/opt" "$staging/root/opt/qemu-guests" "$staging/root/Library" "$staging/root/Library/LaunchDaemons"
ditto -xk "$payload" "$staging/root/opt/qemu-guests"
mv "$staging/root/opt/qemu-guests/macos-firstboot.plist" "$staging/root/Library/LaunchDaemons/com.me.qemu-guests.firstboot.plist"
chmod 644 "$staging/root/Library/LaunchDaemons/com.me.qemu-guests.firstboot.plist"
chmod 755 "$staging/root/opt/qemu-guests/docker"
chmod 644 "$staging/root/opt/qemu-guests/environment" "$staging/root/opt/qemu-guests/verify-macos.sh"
chmod 600 "$staging/root/opt/qemu-guests/backend-key" "$staging/root/opt/qemu-guests/account-password"
pkgbuild --root "$staging/root" --identifier com.me.qemu-guests.bootstrap --version 1 --ownership recommended "$staging/component.pkg"
productbuild --package "$staging/component.pkg" --identifier com.me.qemu-guests.bootstrap --version 1 "$output"
