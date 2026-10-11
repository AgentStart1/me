#!/bin/ash
set -eu
[ -z "$(docker ps -q)" ] || { echo 'Error: running containers prevent network migration.' >&2; exit 1; }
grep -q '"dns": \["172.17.0.1"\]' /etc/docker/daemon.json || { echo 'Error: unexpected Docker DNS configuration.' >&2; exit 1; }
backup=/root/qemu-network-before-gvproxy
[ ! -e "$backup" ] || { echo 'Error: migration backup already exists; inspect before continuing.' >&2; exit 1; }
mkdir -m 700 "$backup"
for path in /etc/docker/daemon.json /etc/udhcpc/udhcpc.conf /etc/resolv.conf /etc/local.d/use-local-dns.start /etc/unbound/unbound.conf; do
    if [ -f "$path" ]; then
        mkdir -p "$backup$(dirname "$path")"
        cp "$path" "$backup$path"
    fi
done
rc-service unbound stop >/dev/null 2>&1 || true
rc-update del unbound default >/dev/null 2>&1 || true
rm -f /etc/local.d/use-local-dns.start /etc/udhcpc/udhcpc.conf
# BusyBox JSON is not a parser: only migrate the exact known plugin DNS value.
sed -i 's/"dns": \["172.17.0.1"\]/"dns": ["192.168.127.1"]/' /etc/docker/daemon.json
printf 'nameserver 192.168.127.1\n' > /etc/resolv.conf
apk del unbound
rm -f /etc/unbound/unbound.conf
printf 'gvproxy-v0.9.0\n' > /etc/qemu-network-backend
