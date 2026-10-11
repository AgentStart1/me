#!/usr/bin/env bash
# Fake device filesystem only; never contacts a connected Android device.
set -euo pipefail
PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fixture="$(mktemp -d)"
trap 'rm -rf "$fixture"' EXIT
mkdir "$fixture/bin" "$fixture/device"
export FAKE_DEVICE_ROOT="$fixture/device"
cat > "$fixture/bin/adb" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
if [ "${1:-}" = -s ]; then shift 2; fi
case "$1" in
    get-state) echo device;;
    shell) shift; command="${*//\/data\/local\/tmp/$FAKE_DEVICE_ROOT}"; bash -c "$command";;
    push)
        [ "${FAIL_PUSH:-0}" != 1 ] || exit 1
        source="$2"
        if command -v cygpath >/dev/null 2>&1; then source="$(cygpath -u "$source")"; fi
        cp "$source" "${3//\/data\/local\/tmp/$FAKE_DEVICE_ROOT}";;
    *) exit 1;;
esac
MOCK
chmod +x "$fixture/bin/adb"
export PATH="$fixture/bin:$PATH"
helper="$PLUGIN_DIR/scripts/adb-device-lock.sh"
for invalid in /data/local/tmp/ /data/local/tmp/../other /data/local/tmp/./other /; do
    if bash "$helper" acquire --lock-path "$invalid" --wait-timeout-seconds 0 >/dev/null 2>&1; then exit 1; fi
done
lease="$FAKE_DEVICE_ROOT/test.lock.d"
options=(--serial fake-device --lock-path /data/local/tmp/test.lock.d --wait-timeout-seconds 0 --poll-seconds 1)
mkdir "$lease"
printf '{"expires_at_epoch":1,"owner_token":"expired-private-token"}\n' > "$lease/lock.json"
bash "$helper" acquire "${options[@]}" --token-file "$fixture/a.token" > "$fixture/a.log" 2>&1 &
a=$!
bash "$helper" acquire "${options[@]}" --token-file "$fixture/b.token" > "$fixture/b.log" 2>&1 &
b=$!
a_status=0; wait "$a" || a_status=$?
b_status=0; wait "$b" || b_status=$?
[[ "$a_status $b_status" == '0 1' || "$a_status $b_status" == '1 0' ]]
token="$fixture/a.token"
[ "$a_status" = 0 ] || token="$fixture/b.token"
grep -Fq "$(cat "$token")" "$lease/lock.json"
! grep -q owner_token "$fixture/a.log" "$fixture/b.log"
printf wrong-owner > "$fixture/wrong.token"
if bash "$helper" release "${options[@]}" --token-file "$fixture/wrong.token" >/dev/null 2>&1; then exit 1; fi
grep -Fq "$(cat "$token")" "$lease/lock.json"
bash "$helper" renew "${options[@]}" --token-file "$token" >/dev/null
bash "$helper" release "${options[@]}" --token-file "$token" >/dev/null
[ ! -e "$lease" ] && [ ! -e "$lease.guard" ]
if FAIL_PUSH=1 bash "$helper" acquire "${options[@]}" --token-file "$fixture/failure.token" >/dev/null 2>&1; then exit 1; fi
[ ! -e "$lease" ] && [ ! -e "$lease.guard" ]
mkdir "$lease.guard"
if bash "$helper" acquire "${options[@]}" --token-file "$fixture/busy.token" >/dev/null 2>&1; then exit 1; fi
[ -d "$lease.guard" ] && [ ! -e "$lease" ]
rmdir "$lease.guard"
status=0
bash "$helper" run "${options[@]}" --token-file "$fixture/run.token" -- bash -c 'exit 23' >/dev/null || status=$?
[ "$status" = 23 ] && [ ! -e "$lease" ] && [ ! -e "$lease.guard" ]
echo 'PASS: fake-device expiry race, owner refusal, renewal, atomic publication, upload failure, interrupted guard and command status'
