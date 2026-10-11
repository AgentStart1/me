#!/bin/bash
# Isolated configuration and daemon lifecycle tests; no VM or network access.
set -euo pipefail
PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MOCK_DIR="$(mktemp -d)"
trap 'rm -rf "$MOCK_DIR"' EXIT
export QEMU_ALPINE_BASE_DIR="$MOCK_DIR" QEMU_ALPINE_SKIP_MSYS2_PATH=1
source "${PLUGIN_DIR}/scripts/vm-utils.sh"
assert_equals() { [ "$1" = "$2" ] || { echo "FAIL: $3 ($2)" >&2; exit 1; }; }
is_windows() { return 0; }
load_profile "${PLUGIN_DIR}/profiles/dev.profile"
assert_equals 20015 "$TESTCONTAINERS_PORT_END" 'Windows profile default'
mappings="$(build_forward_mappings)"
assert_equals 21 "$(wc -l <<< "$mappings" | tr -d ' ')" 'control/custom/default forwards'
assert_equals 'socket,id=net0,connect=127.0.0.1:19200' "$(build_netdev_value)" 'one QEMU connection'
is_windows() { return 1; }
load_profile "${PLUGIN_DIR}/profiles/dev.profile"
assert_equals 20255 "$TESTCONTAINERS_PORT_END" 'Linux profile default'
TESTCONTAINERS_PORT_END=20511
assert_equals 517 "$(build_forward_mappings | wc -l | tr -d ' ')" '512 data plus control/custom forwards'
TESTCONTAINERS_PORT_END=20512
if build_netdev_value >/dev/null 2>&1; then echo 'FAIL: 513 ports accepted'; exit 1; fi
TESTCONTAINERS_PORT_END=20015
for PORT_FORWARD in 2222:80 2375:80 20000:80 9090:80,9090:81; do
    if build_netdev_value >/dev/null 2>&1; then echo "FAIL: collision accepted"; exit 1; fi
done
PORT_FORWARD=
for bounds in '0 15' '20000 65536' '20001 20000'; do
    read -r TESTCONTAINERS_PORT_START TESTCONTAINERS_PORT_END <<< "$bounds"
    if build_netdev_value >/dev/null 2>&1; then echo 'FAIL: invalid range accepted'; exit 1; fi
done
TESTCONTAINERS_PORT_START=20000 TESTCONTAINERS_PORT_END=20015
assert_equals '32768 60999' "$(guest_outbound_port_range)" 'default outbound range'
TESTCONTAINERS_PORT_START=32768 TESTCONTAINERS_PORT_END=33279
assert_equals '33280 60999' "$(guest_outbound_port_range)" 'low overlap removed'
TESTCONTAINERS_PORT_START=60488 TESTCONTAINERS_PORT_END=60999
assert_equals '32768 60487' "$(guest_outbound_port_range)" 'high overlap removed'

render_template "${PLUGIN_DIR}/templates/dockerd-with-port-range.sh.tpl" "$MOCK_DIR/wrapper" \
    TESTCONTAINERS_PORT_START 20000 TESTCONTAINERS_PORT_END 20015 \
    OUTBOUND_PORT_START 32768 OUTBOUND_PORT_END 60999
# Replace absolute guest commands only in this isolated fixture.
sed -i 's@/usr/bin/dockerd@mock-dockerd@g; s@/usr/bin/docker@mock-docker@g' "$MOCK_DIR/wrapper"
sed -i "s@/run/qemu-docker-publish-pool.ready@${MOCK_DIR}/publish-ready@g" "$MOCK_DIR/wrapper"
mkdir "$MOCK_DIR/bin"
export MOCK_DIR PATH="$MOCK_DIR/bin:$PATH"
cat > "$MOCK_DIR/bin/sysctl" <<'MOCK'
#!/bin/bash
printf '%s\n' "${*:2}" >> "$MOCK_DIR/sysctl-log"
printf '%s\n' "${*:2}" > "$MOCK_DIR/current-range"
if [ "${FAIL_RESTORE:-0}" = 1 ] && [[ "$*" == *'32768 60999'* ]]; then exit 1; fi
MOCK
cat > "$MOCK_DIR/bin/mock-dockerd" <<'MOCK'
#!/bin/bash
cat "$MOCK_DIR/current-range" > "$MOCK_DIR/cached-range"
echo $$ > "$MOCK_DIR/daemon.pid"
if [ "${FAIL_DAEMON:-0}" = 1 ]; then exit 42; fi
touch "$MOCK_DIR/ready"
if [ "${WAIT_DAEMON:-0}" = 1 ]; then while :; do sleep 1; done; fi
while ! grep -q '32768 60999' "$MOCK_DIR/current-range"; do sleep 0.01; done
exit 7
MOCK
cat > "$MOCK_DIR/bin/mock-docker" <<'MOCK'
#!/bin/bash
shift 2
case "$1" in
    info) [ -f "$MOCK_DIR/ready" ];;
    ps) [ "${EXISTING_MAPPING:-0}" != 1 ] || echo existing-container;;
    import) echo seed-image;;
    run) cat "$MOCK_DIR/current-range" > "$MOCK_DIR/cache-on-mapping"; echo seed-container;;
    port) echo "127.0.0.1:${PROBE_PORT:-20000}";;
    rm|image) echo "$*" >> "$MOCK_DIR/seed-cleanup";;
    *) exit 1;;
esac
MOCK
cat > "$MOCK_DIR/bin/tar" <<'MOCK'
#!/bin/bash
touch "$2"
MOCK
chmod +x "$MOCK_DIR/bin/"*
status=0
bash "$MOCK_DIR/wrapper" || status=$?
assert_equals 7 "$status" 'daemon exit status preserved'
assert_equals 'net.ipv4.ip_local_port_range=20000 20015' "$(cat "$MOCK_DIR/cached-range")" 'Docker initializes matching pool'
assert_equals 'net.ipv4.ip_local_port_range=20000 20015' "$(cat "$MOCK_DIR/cache-on-mapping")" 'fresh allocator seeded before outbound restoration'
assert_equals 'net.ipv4.ip_local_port_range=32768 60999' "$(cat "$MOCK_DIR/current-range")" 'outbound restored after readiness'
rm "$MOCK_DIR/ready"
export FAIL_DAEMON=1
status=0
bash "$MOCK_DIR/wrapper" 2>"$MOCK_DIR/failure" || status=$?
assert_equals 42 "$status" 'startup failure preserved'
assert_equals 'net.ipv4.ip_local_port_range=32768 60999' "$(cat "$MOCK_DIR/current-range")" 'outbound restored after failure'
grep -q 'exited before initializing' "$MOCK_DIR/failure"
unset FAIL_DAEMON
export PROBE_PORT=40000
status=0
bash "$MOCK_DIR/wrapper" 2>"$MOCK_DIR/wrong-pool" || status=$?
assert_equals 1 "$status" 'wrong automatic pool fails startup'
grep -q 'outside the QEMU forwarding range' "$MOCK_DIR/wrong-pool"
grep -q 'rm -f seed-container' "$MOCK_DIR/seed-cleanup"
unset PROBE_PORT
export EXISTING_MAPPING=1
rm "$MOCK_DIR/cache-on-mapping"
status=0
bash "$MOCK_DIR/wrapper" || status=$?
assert_equals 7 "$status" 'restored mapping initializes allocator without spare pool port'
[ ! -e "$MOCK_DIR/cache-on-mapping" ]
unset EXISTING_MAPPING
export FAIL_RESTORE=1
status=0
bash "$MOCK_DIR/wrapper" || status=$?
assert_equals 1 "$status" 'outbound restore failure is not hidden'
unset FAIL_RESTORE
rm "$MOCK_DIR/ready"
export WAIT_DAEMON=1
bash "$MOCK_DIR/wrapper" &
wrapper_pid=$!
for ((attempt=0; attempt<100; attempt++)); do
    [ -f "$MOCK_DIR/publish-ready" ] && break
    sleep 0.05
done
[ -f "$MOCK_DIR/publish-ready" ]
assert_equals '20000 20015' "$(cat "$MOCK_DIR/publish-ready")" 'readiness only after pool seeding and outbound restore'
kill -TERM "$wrapper_pid"
status=0
wait "$wrapper_pid" || status=$?
assert_equals 143 "$status" 'termination status preserved'
[ ! -e "$MOCK_DIR/publish-ready" ]
if kill -0 "$(cat "$MOCK_DIR/daemon.pid")" 2>/dev/null; then echo 'FAIL: child daemon survived termination'; exit 1; fi
echo 'PASS: platform defaults, gvproxy mappings, collisions, outbound separation and daemon lifecycle'
