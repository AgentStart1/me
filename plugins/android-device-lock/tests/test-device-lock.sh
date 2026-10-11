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
    shell)
        if [ "${FAIL_REMOTE_RM:-0}" = 1 ] && [[ "${2:-}" == 'rm -rf '* ]]; then exit 1; fi
        shift; command="${*//\/data\/local\/tmp/$FAKE_DEVICE_ROOT}"; bash -c "$command";;
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
cat > "$lease/lock.json" <<'JSON'
{"project_dir":"/fixture","test_name":"expired-fixture","requested_at_utc":"1970-01-01T00:00:00Z","acquired_at_utc":"1970-01-01T00:00:00Z","max_timeout_seconds":1,"expires_at_epoch":1,"host":"fixture-host","pid":1,"owner_token":"expired-private-token"}
JSON
cp "$lease/lock.json" "$fixture/valid-record"
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
mkdir "$lease"
printf '{"expires_at_epoch":1,"owner_token":"must-stay-private", broken}\n' > "$lease/lock.json"
cp "$lease/lock.json" "$fixture/corrupt-before"
if bash "$helper" acquire "${options[@]}" --token-file "$fixture/corrupt.token" > "$fixture/corrupt.log" 2>&1; then exit 1; fi
cmp "$fixture/corrupt-before" "$lease/lock.json"
! grep -q must-stay-private "$fixture/corrupt.log"
for kind in boolean missing duplicate nonfinite; do
    python3 - "$fixture/valid-record" "$lease/lock.json" "$kind" <<'PY'
import json,sys
from pathlib import Path
record=json.loads(Path(sys.argv[1]).read_text())
kind=sys.argv[3]
if kind == 'boolean': record['expires_at_epoch']=True
if kind == 'missing': del record['host']
if kind == 'nonfinite': record['extra']=float('nan')
content=json.dumps(record)
if kind == 'duplicate': content=content[:-1]+',"expires_at_epoch":1}'
Path(sys.argv[2]).write_text(content)
PY
    cp "$lease/lock.json" "$fixture/invalid-before"
    if bash "$helper" acquire "${options[@]}" --token-file "$fixture/invalid.token" >/dev/null 2>&1; then exit 1; fi
    cmp "$fixture/invalid-before" "$lease/lock.json"
done
rm "$lease/lock.json"; rmdir "$lease"
bash "$helper" acquire "${options[@]}" --token-file "$fixture/escaped.token" --test-name $'quoted "name"\nnext line ${owner_token}\n' >/dev/null
bash "$helper" renew "${options[@]}" --token-file "$fixture/escaped.token" >/dev/null
grep -Fq '\nnext line ${owner_token}\n' "$lease/lock.json"
python3 - "$lease/lock.json" <<'PY'
import json,sys
from pathlib import Path
record=json.loads(Path(sys.argv[1]).read_text())
assert record['test_name'] == 'quoted "name"\nnext line ${owner_token}\n'
assert isinstance(record['expires_at_epoch'],int)
PY
bash "$helper" release "${options[@]}" --token-file "$fixture/escaped.token" >/dev/null
status=0
bash "$helper" run "${options[@]}" --token-file "$fixture/run.token" -- bash -c 'exit 23' >/dev/null || status=$?
[ "$status" = 23 ] && [ ! -e "$lease" ] && [ ! -e "$lease.guard" ]

# Failed remote deletion retains the recovery token through both entry points.
for mode in release run; do
    recovery_token="$fixture/$mode-recovery.token"
    if [ "$mode" = release ]; then
        bash "$helper" acquire "${options[@]}" --token-file "$recovery_token" >/dev/null
        cp "$recovery_token" "$fixture/token-before"
        status=0
        FAIL_REMOTE_RM=1 bash "$helper" release "${options[@]}" --token-file "$recovery_token" >"$fixture/release-failure.log" 2>&1 || status=$?
        cmp "$fixture/token-before" "$recovery_token"
    else
        status=0
        FAIL_REMOTE_RM=1 bash "$helper" run "${options[@]}" --token-file "$recovery_token" -- true >"$fixture/release-failure.log" 2>&1 || status=$?
    fi
    [ "$status" -ne 0 ] && [ -s "$recovery_token" ] && [ -f "$lease/lock.json" ] && [ ! -e "$lease.guard" ]
    grep -Fq "$(cat "$recovery_token")" "$lease/lock.json"
    ! grep -q 'Released Android device lock' "$fixture/release-failure.log"
    bash "$helper" release "${options[@]}" --token-file "$recovery_token" >/dev/null
    [ ! -e "$recovery_token" ] && [ ! -e "$lease" ]
done
status=0
FAIL_REMOTE_RM=1 bash "$helper" run "${options[@]}" --token-file "$fixture/failed-run.token" -- bash -c 'exit 23' >/dev/null 2>&1 || status=$?
[ "$status" = 23 ] && [ -s "$fixture/failed-run.token" ] && [ -f "$lease/lock.json" ]
bash "$helper" release "${options[@]}" --token-file "$fixture/failed-run.token" >/dev/null

echo 'PASS: fake-device races, typed JSON/control characters, corrupt-state retention, owner refusal, renewal, atomic publication, failure cleanup and command status'
