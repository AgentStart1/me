#!/usr/bin/env bash
set -euo pipefail
PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ "$(uname -s)" == Linux* ]] || { echo 'SKIP: Linux wrapper test'; exit 0; }
fixture="$(mktemp -d)"
trap 'rm -r "$fixture"' EXIT
mkdir -p "$fixture/bin" "$fixture/state/vms"
printf '#!/bin/sh\nexit 0\n' > "$fixture/bin/curl"
chmod +x "$fixture/bin/curl"
cp "$fixture/bin/curl" "$fixture/bin/docker"
printf '%s\n' "$$" > "$fixture/state/vms/alpine-docker.pid"
cat > "$fixture/command.sh" <<'COMMAND'
#!/usr/bin/env bash
set -euo pipefail
[[ "$DOCKER_HOST" == tcp://127.0.0.1:2375 ]]
[[ "$TESTCONTAINERS_HOST_OVERRIDE" == 127.0.0.1 ]]
[[ "$TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE" == /var/run/docker.sock ]]
[[ -z "${TESTCONTAINERS_RYUK_DISABLED:-}" ]]
[[ "$1" == 'argument with spaces' ]]
exit 23
COMMAND
result=0
PATH="$fixture/bin:$PATH" QEMU_DOCKER_PROXY_DIR="$fixture/bin" QEMU_ALPINE_BASE_DIR="$fixture/state" TESTCONTAINERS_RYUK_DISABLED=true \
  bash "$PLUGIN_DIR/scripts/run-testcontainers.sh" -- bash "$fixture/command.sh" 'argument with spaces' || result=$?
[[ "$result" == 23 ]] || { echo "FAIL: Linux auto metrics blocked or changed command status: $result"; exit 1; }
echo 'PASS: Linux default profile runs tests, preserves arguments/exit status, and enables guest Ryuk without PowerShell'
