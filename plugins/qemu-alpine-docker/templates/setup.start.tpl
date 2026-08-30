#!/bin/ash
set -eu
exec >/dev/ttyS0 2>&1
trap 'status=$?; if [ "$status" -ne 0 ]; then echo "Unattended installation failed with status $status"; poweroff -f; fi' EXIT

ip link set eth0 up
udhcpc -i eth0 -q -n -t 10

ALPINE_BRANCH="$(sed -n '1p' /mirror-config)"
ALPINE_MIRROR_BASE="$(sed -n '2p' /mirror-config)"
SELECTED_MIRROR="$(ALPINE_FALLBACK_MIRROR="{{ALPINE_FALLBACK_MIRROR}}" \
    /usr/local/libexec/select-apk-mirror "$ALPINE_BRANCH" "$ALPINE_MIRROR_BASE" /answers)"
echo "Selected Alpine mirror: ${SELECTED_MIRROR}"
apk add cgroupfs-mount docker docker-cli-compose openssh unbound
rc-update add cgroups default
rc-update add docker default
rc-update add sshd default
rc-update add unbound default
rc-update add sysctl boot 2>/dev/null || true
rc-update add local default

mkdir -p /etc/docker
cp /docker-daemon.json /etc/docker/daemon.json
chmod 0644 /etc/docker/daemon.json

mkdir -p /etc/udhcpc
cp /udhcpc.conf /etc/udhcpc/udhcpc.conf
chmod 0644 /etc/udhcpc/udhcpc.conf

touch /etc/qemu-alpine-docker-image
# Do not copy provisioning-only files into the installed system.
rm -f /etc/local.d/setup.start
rm -f /docker-daemon.json /mirror-config /udhcpc.conf /usr/local/libexec/select-apk-mirror

ERASE_DISKS=/dev/vda setup-alpine -e -f /answers
trap - EXIT
poweroff
