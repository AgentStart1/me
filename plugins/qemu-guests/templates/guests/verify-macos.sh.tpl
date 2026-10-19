#!/bin/bash
set -euo pipefail
. /opt/qemu-guests/environment
docker version
/usr/bin/curl --noproxy 127.0.0.1 -fsS http://127.0.0.1:2375/version >/dev/null
for ((port={{POOL_START}}; port<={{POOL_END}}; port++)); do
    /usr/bin/nc -z -G 1 127.0.0.1 "$port"
done
