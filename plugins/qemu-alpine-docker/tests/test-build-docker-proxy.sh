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
    *'ash ./guest-build.sh'*)
        if [ -n "${PROXY_EVENTS:-}" ]; then
            echo "start ${PROXY_CALL}" >> "$PROXY_EVENTS"
            sleep 1
            echo "end ${PROXY_CALL}" >> "$PROXY_EVENTS"
        fi
        [ "${PROXY_FAIL:-}" != build ] ;;
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
[ ! -d "$TEST_DIR/home/run/docker-proxy-build.lock" ]
[ ! -d "$TEST_DIR/output/.docker-proxy-build.lock" ]
export PROXY_EVENTS="$TEST_DIR/events"
PROXY_CALL=first bash "$PLUGIN_DIR/scripts/build-docker-proxy.sh" --profile "$TEST_DIR/test.profile" > "$TEST_DIR/first.log" 2>&1 &
first_pid=$!
for ((attempt=0; attempt<100; attempt++)); do
    [ -s "$PROXY_EVENTS" ] && break
    sleep 0.05
done
[ -s "$PROXY_EVENTS" ]
PROXY_CALL=second QEMU_DOCKER_PROXY_DIR="$TEST_DIR/other-output" bash "$PLUGIN_DIR/scripts/build-docker-proxy.sh" --profile "$TEST_DIR/test.profile" > "$TEST_DIR/second.log" 2>&1 &
second_pid=$!
wait "$first_pid"
wait "$second_pid"
[ "$(cat "$PROXY_EVENTS")" = $'start first\nend first\nstart second\nend second' ]
[[ "$(cat "$TEST_DIR/second.log")" == *'Waiting for another Docker proxy build'* ]]
unset PROXY_EVENTS
echo 'PASS: concurrent builds with different output directories serialize the entire VM build'

output_lock="$TEST_DIR/output/.docker-proxy-build.lock"
mkdir "$output_lock"
printf '%s\n' "$$" > "$output_lock/owner.pid"
if QEMU_DOCKER_BUILD_LOCK_TIMEOUT=1 bash "$PLUGIN_DIR/scripts/build-docker-proxy.sh" --profile "$TEST_DIR/test.profile" > "$TEST_DIR/timeout.log" 2>&1; then
    echo 'FAIL: busy output lock did not time out'; exit 1
fi
[[ "$(cat "$TEST_DIR/timeout.log")" == *'timed out'* ]]
[ "$(cat "$output_lock/owner.pid")" = "$$" ]
[ ! -d "$TEST_DIR/home/run/docker-proxy-build.lock" ]
echo 'PASS: timeout preserves another owner and releases the acquired VM lock'
bash "$PLUGIN_DIR/scripts/build-docker-proxy.sh" --profile "$TEST_DIR/test.profile" > "$TEST_DIR/signal.log" 2>&1 &
signal_pid=$!
for ((attempt=0; attempt<100; attempt++)); do
    if [[ "$(cat "$TEST_DIR/signal.log")" == *'Waiting for another Docker proxy build'* ]]; then break; fi
    sleep 0.05
done
kill -TERM "$signal_pid"
if wait "$signal_pid"; then echo 'FAIL: terminated waiter returned success'; exit 1; fi
[ ! -d "$TEST_DIR/home/run/docker-proxy-build.lock" ]
[ "$(cat "$output_lock/owner.pid")" = "$$" ]
echo 'PASS: termination releases only the waiter-owned VM lock'
printf '999999999\n' > "$output_lock/owner.pid"
if bash "$PLUGIN_DIR/scripts/build-docker-proxy.sh" --profile "$TEST_DIR/test.profile" > "$TEST_DIR/stale.log" 2>&1; then
    echo 'FAIL: stale lock was silently stolen'; exit 1
fi
[[ "$(cat "$TEST_DIR/stale.log")" == *'stale proxy build lock'* ]]
[ ! -d "$TEST_DIR/home/run/docker-proxy-build.lock" ]
echo 'PASS: stale locks produce actionable recovery instructions'
