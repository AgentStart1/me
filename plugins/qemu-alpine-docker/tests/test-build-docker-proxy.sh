#!/bin/bash
# Exercise bootstrap SSH without a host compiler or an existing proxy.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_DIR="$(mktemp -d)"
trap 'rm -rf "$TEST_DIR"' EXIT
mkdir -p "$TEST_DIR/bin" "$TEST_DIR/home/vms" "$TEST_DIR/output"
printf 'VM_NAME=test-vm\nSSH_PORT=2299\n' > "$TEST_DIR/test.profile"
printf '%s\n' "$$" > "$TEST_DIR/home/vms/test-vm.pid"
cat > "$TEST_DIR/bin/ssh" <<'MOCK'
#!/bin/bash
printf '%s\n' "$*" >> "$PROXY_SSH_LOG"
case "${*: -1}" in
    mktemp*) echo /tmp/qemu-docker-proxy.mock123 ;;
    *'tar -xf -'*) tar -tf - > "$PROXY_ARCHIVE_LOG" ;;
    *'ash ./guest-build.sh'*) [ "${PROXY_FAIL:-}" != build ] ;;
    cat*) [ "${PROXY_FAIL:-}" != download ] || exit 1; printf 'proxy executable' ;;
    'rm -rf'*) ;;
    *) exit 1 ;;
esac
MOCK
cat > "$TEST_DIR/bin/go" <<'MOCK'
#!/bin/bash
echo 'Host Go must not be used' >&2
exit 99
MOCK
chmod +x "$TEST_DIR/bin/ssh" "$TEST_DIR/bin/go"
export PATH="$TEST_DIR/bin:$PATH" QEMU_ALPINE_SKIP_MSYS2_PATH=1
export QEMU_ALPINE_BASE_DIR="$TEST_DIR/home" QEMU_DOCKER_PROXY_DIR="$TEST_DIR/output"
export PROXY_SSH_LOG="$TEST_DIR/ssh.log" PROXY_ARCHIVE_LOG="$TEST_DIR/archive.log"
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) name=docker.exe; target="'windows' 'amd64'" ;; *) name=docker; target="'linux' 'amd64'" ;; esac
bash "$PLUGIN_DIR/scripts/build-docker-proxy.sh" --profile "$TEST_DIR/test.profile"
[ "$(cat "$TEST_DIR/output/$name")" = 'proxy executable' ]
[[ "$(cat "$PROXY_SSH_LOG")" == *"$target"* ]]
[[ "$(cat "$PROXY_ARCHIVE_LOG")" == *'./main.go'* ]]
[[ "$(cat "$PROXY_ARCHIVE_LOG")" == *'build-docker-proxy.sh.tpl'* ]]
[[ "$(cat "$PROXY_SSH_LOG")" == *"rm -rf -- '/tmp/qemu-docker-proxy.mock123'"* ]]
echo 'PASS: bootstrap transfer, target, download, cleanup, and no host Go'
for failure in build download; do
    printf previous > "$TEST_DIR/output/$name"
    : > "$PROXY_SSH_LOG"
    if PROXY_FAIL="$failure" bash "$PLUGIN_DIR/scripts/build-docker-proxy.sh" --profile="$TEST_DIR/test.profile"; then
        echo "FAIL: $failure reported success" >&2; exit 1
    fi
    [ "$(cat "$TEST_DIR/output/$name")" = previous ]
    [[ "$(cat "$PROXY_SSH_LOG")" == *"rm -rf -- '/tmp/qemu-docker-proxy.mock123'"* ]]
    shopt -s nullglob
    leftovers=("$TEST_DIR/output"/.docker-proxy.*)
    [ "${#leftovers[@]}" -eq 0 ]
    echo "PASS: $failure preserves existing proxy and cleans staging"
done
