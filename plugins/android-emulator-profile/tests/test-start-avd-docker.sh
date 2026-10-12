#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TMP_DIR="$(mktemp -d)"

# shellcheck source=/dev/null
source "${PLUGIN_DIR}/scripts/profile-utils.sh"

assert_profile_arg_case() {
    local emulator_output avdmanager_output
    local EMULATOR_FLAG_Mixed_Case=true
    local EMULATOR_VALUE_Custom_Value=preserved
    local AVDMANAGER_FLAG_verbose=true
    local AVDMANAGER_VALUE_Custom_Path=/tmp/avd
    local -a emulator_args=()
    local -a avdmanager_args=()

    append_args_from_env emulator_args EMULATOR -
    append_args_from_env avdmanager_args AVDMANAGER --

    emulator_output="$(printf '%s\n' "${emulator_args[@]}")"
    avdmanager_output="$(printf '%s\n' "${avdmanager_args[@]}")"

    grep -qx -- "-Mixed-Case" <<< "$emulator_output"
    grep -qx -- "-Custom-Value" <<< "$emulator_output"
    grep -qx -- "--verbose" <<< "$avdmanager_output"
    grep -qx -- "--Custom-Path" <<< "$avdmanager_output"
}

cleanup() {
    if [ -n "${holding_driver:-}" ]; then kill -TERM "$holding_driver" 2>/dev/null || true; wait "$holding_driver" 2>/dev/null || true; fi
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

HOME_DIR="${TMP_DIR}/android-home"
SDK_HOME="${TMP_DIR}/android-sdk"
AVD_HOME="${TMP_DIR}/custom-avd-home"
PROFILE_PATH="${TMP_DIR}/mobile.profile"
EMULATOR_ARGS_LOG="${TMP_DIR}/emulator-args.log"
EMULATOR_ENV_LOG="${TMP_DIR}/emulator-env.log"
EMULATOR_CONFIG_LOG="${TMP_DIR}/emulator-config.log"
ADB_ARGS_LOG="${TMP_DIR}/adb-args.log"
START_AVD_OUT="${TMP_DIR}/start-avd.out"
START_AVD_ERR="${TMP_DIR}/start-avd.err"
CREATE_AVD_OUT="${TMP_DIR}/create-avd.out"
CREATE_AVD_ERR="${TMP_DIR}/create-avd.err"

mkdir -p "${AVD_HOME}/docker-test-avd.avd" \
    "${AVD_HOME}/unrelated.avd" \
    "${SDK_HOME}/cmdline-tools/latest/bin" \
    "${SDK_HOME}/emulator" \
    "${SDK_HOME}/platform-tools"
touch "${AVD_HOME}/docker-test-avd.avd/stale.lock"
touch "${AVD_HOME}/unrelated.avd/running.lock"
printf existing-data > "${AVD_HOME}/docker-test-avd.avd/userdata-qemu.img"
cat > "${AVD_HOME}/docker-test-avd.avd/config.ini" <<'CONFIG'
hw.gpu.enabled=no
hw.gpu.mode=auto
hw.accelerometer_uncalibrated=yes
disk.dataPartition.size=2G
duplicate.key=old-first
duplicate.key=old-second
CONFIG

cat > "${SDK_HOME}/emulator/emulator" <<'EMULATOR'
#!/usr/bin/env bash
set -euo pipefail
printf "%s\n" "$@" > "${EMULATOR_ARGS_LOG}"
printf "DISPLAY=%s\n" "${DISPLAY:-}" > "${EMULATOR_ENV_LOG}"
cp "${ANDROID_AVD_HOME}/docker-test-avd.avd/config.ini" "${EMULATOR_CONFIG_LOG}"
if [ "${FAKE_EMULATOR_HOLD:-0}" = 1 ]; then
    echo $$ > "$FAKE_EMULATOR_PID"
    trap 'exit 0' TERM INT
    while :; do sleep 0.1; done
fi
exit 0
EMULATOR

cat > "${SDK_HOME}/platform-tools/adb" <<'ADB'
#!/usr/bin/env bash
set -euo pipefail
printf "%s\n" "$@" >> "${ADB_ARGS_LOG}"
exit 0
ADB

cat > "${SDK_HOME}/cmdline-tools/latest/bin/sdkmanager" <<'SDKMANAGER'
#!/usr/bin/env bash
set -euo pipefail
if [ "${1:-}" = "--list_installed" ]; then
    printf '%s\n' 'system-images;android-36.1;google_apis;x86_64 | 1 | installed'
    printf '%s\n' 'system-images;android-36.1;google_apis;arm64-v8a | 1 | installed'
fi
exit 0
SDKMANAGER

cat > "${SDK_HOME}/cmdline-tools/latest/bin/avdmanager" <<'AVDMANAGER'
#!/usr/bin/env bash
set -euo pipefail
if [ "${1:-}" = "list" ] && [ "${2:-}" = "avd" ]; then
    printf 'Name: %s\n' "${LISTED_AVD_NAME:-docker-test-avd}"
else
    printf '%s\n' "$@" > "$AVDMANAGER_ARGS_LOG"
fi
exit 0
AVDMANAGER

chmod +x \
    "${SDK_HOME}/cmdline-tools/latest/bin/avdmanager" \
    "${SDK_HOME}/cmdline-tools/latest/bin/sdkmanager" \
    "${SDK_HOME}/emulator/emulator" \
    "${SDK_HOME}/platform-tools/adb"

cat > "$PROFILE_PATH" <<PROFILE
ANDROID_HOME=${SDK_HOME}
ANDROID_AVD_HOME=${AVD_HOME}
AVD_NAME=docker-test-avd
SYS_IMG_PKG='system-images;android-36.1;google_apis'
EMULATOR_DISPLAY=:42
EMULATOR_FLAG_no_audio=true
EMULATOR_FLAG_no_snapshot=true
EMULATOR_FLAG_verbose=false
EMULATOR_FLAG_Mixed_Case=true
EMULATOR_VALUE_gpu=swiftshader_indirect
EMULATOR_VALUE_memory=2048
EMULATOR_VALUE_Custom_Value=preserved
EMULATOR_CONFIG_hw__gpu__enabled=yes
EMULATOR_CONFIG_hw__gpu__mode=swiftshader_indirect
EMULATOR_CONFIG_hw__accelerometer_uncalibrated=no
EMULATOR_CONFIG_disk__dataPartition__size=10G
EMULATOR_CONFIG_duplicate__key=final
PROFILE

# Shell syntax in a value must remain data and must not run project commands.
printf 'TEST_LITERAL=value; touch %s/should-not-exist\n' "$TMP_DIR" > "$TMP_DIR/literal.profile"
load_profile "$TMP_DIR/literal.profile"
[ ! -e "$TMP_DIR/should-not-exist" ]
[[ "$TEST_LITERAL" == 'value; touch '* ]]

# Refusing an unapproved wipe must leave existing config and locks unchanged.
cp "${AVD_HOME}/docker-test-avd.avd/config.ini" "$TMP_DIR/config-before"
if HOME="$HOME_DIR" bash "${PLUGIN_DIR}/scripts/start-avd.sh" "$PROFILE_PATH" > "$START_AVD_OUT" 2> "$START_AVD_ERR"; then
    echo 'FAIL: existing AVD lock ignored' >&2; exit 1
fi
cmp "$TMP_DIR/config-before" "${AVD_HOME}/docker-test-avd.avd/config.ini"
grep -q 'Existing AVD lock' "$START_AVD_ERR"
[ -e "${AVD_HOME}/docker-test-avd.avd/stale.lock" ]
rm "${AVD_HOME}/docker-test-avd.avd/stale.lock"
if HOME="$HOME_DIR" bash "${PLUGIN_DIR}/scripts/start-avd.sh" "$PROFILE_PATH" > "$START_AVD_OUT" 2> "$START_AVD_ERR"; then
    echo 'FAIL: AVD resize silently allowed data wipe' >&2; exit 1
fi
cmp "$TMP_DIR/config-before" "${AVD_HOME}/docker-test-avd.avd/config.ini"
grep -q EMULATOR_ALLOW_DATA_WIPE "$START_AVD_ERR"
printf '\nEMULATOR_ALLOW_DATA_WIPE=true\n' >> "$PROFILE_PATH"

echo "Running start-avd.sh smoke test with fake emulator commands..."

assert_profile_arg_case

if ! HOME="$HOME_DIR" \
    bash "${PLUGIN_DIR}/scripts/create-avd.sh" "$PROFILE_PATH" > "$CREATE_AVD_OUT" 2> "$CREATE_AVD_ERR"; then
    echo "Error: create-avd.sh failed." >&2
    cat "$CREATE_AVD_OUT" >&2
    cat "$CREATE_AVD_ERR" >&2
    exit 1
fi

grep -q "AVD 'docker-test-avd' already exists." "$CREATE_AVD_ERR"
HOME="$HOME_DIR" LISTED_AVD_NAME=docker-test-avd-extra AVDMANAGER_ARGS_LOG="$TMP_DIR/create-args" \
    bash "${PLUGIN_DIR}/scripts/create-avd.sh" "$PROFILE_PATH" > "$CREATE_AVD_OUT" 2> "$CREATE_AVD_ERR"
grep -qx create "$TMP_DIR/create-args"

if ! HOME="$HOME_DIR" \
    EMULATOR_ARGS_LOG="$EMULATOR_ARGS_LOG" \
    EMULATOR_ENV_LOG="$EMULATOR_ENV_LOG" \
    EMULATOR_CONFIG_LOG="$EMULATOR_CONFIG_LOG" \
    ADB_ARGS_LOG="$ADB_ARGS_LOG" \
    bash "${PLUGIN_DIR}/scripts/start-avd.sh" "$PROFILE_PATH" > "$START_AVD_OUT" 2> "$START_AVD_ERR"; then
    echo "Error: start-avd.sh failed." >&2
    cat "$START_AVD_OUT" >&2
    cat "$START_AVD_ERR" >&2
    exit 1
fi

grep -q "Starting emulator..." "$START_AVD_OUT"
grep -q "Emulator process has exited." "$START_AVD_OUT"
grep -q -- "-avd" "$EMULATOR_ARGS_LOG"
grep -q "docker-test-avd" "$EMULATOR_ARGS_LOG"
grep -q -- "-wipe-data" "$EMULATOR_ARGS_LOG"
grep -q -- "-no-audio" "$EMULATOR_ARGS_LOG"
grep -q -- "-no-snapshot" "$EMULATOR_ARGS_LOG"
grep -q -- "-gpu" "$EMULATOR_ARGS_LOG"
grep -q "swiftshader_indirect" "$EMULATOR_ARGS_LOG"
grep -q -- "-memory" "$EMULATOR_ARGS_LOG"
grep -q "2048" "$EMULATOR_ARGS_LOG"
grep -q -- "-Mixed-Case" "$EMULATOR_ARGS_LOG"
grep -q -- "-Custom-Value" "$EMULATOR_ARGS_LOG"
grep -q "preserved" "$EMULATOR_ARGS_LOG"
grep -q "DISPLAY=:42" "$EMULATOR_ENV_LOG"
grep -qx "hw.gpu.enabled=yes" "$EMULATOR_CONFIG_LOG"
grep -qx "hw.gpu.mode=swiftshader_indirect" "$EMULATOR_CONFIG_LOG"
grep -qx "hw.accelerometer_uncalibrated=no" "$EMULATOR_CONFIG_LOG"
grep -qx "disk.dataPartition.size=10G" "$EMULATOR_CONFIG_LOG"
grep -qx "duplicate.key=final" "$EMULATOR_CONFIG_LOG"

if [ "$(grep -c '^duplicate.key=' "$EMULATOR_CONFIG_LOG")" -ne 1 ]; then
    echo "Error: duplicate config.ini keys were not collapsed." >&2
    exit 1
fi

if grep -q -- "-verbose" "$EMULATOR_ARGS_LOG"; then
    echo "Error: false emulator flag was unexpectedly passed." >&2
    exit 1
fi

[ -e "${AVD_HOME}/unrelated.avd/running.lock" ]
[ ! -e "${AVD_HOME}/docker-test-avd.avd/config.ini.profile-start.guard" ]
[ ! -e "$ADB_ARGS_LOG" ]

if ! HOME="$HOME_DIR" \
    EMULATOR_ARGS_LOG="$EMULATOR_ARGS_LOG" \
    EMULATOR_ENV_LOG="$EMULATOR_ENV_LOG" \
    EMULATOR_CONFIG_LOG="$EMULATOR_CONFIG_LOG" \
    ADB_ARGS_LOG="$ADB_ARGS_LOG" \
    bash "${PLUGIN_DIR}/scripts/start-avd.sh" "$PROFILE_PATH" > "$START_AVD_OUT" 2> "$START_AVD_ERR"; then
    echo "Error: second start-avd.sh run failed." >&2
    cat "$START_AVD_OUT" >&2
    cat "$START_AVD_ERR" >&2
    exit 1
fi

if grep -q -- "-wipe-data" "$EMULATOR_ARGS_LOG"; then
    echo "Error: -wipe-data was unexpectedly passed after data partition size matched." >&2
    exit 1
fi

# A new AVD without userdata can set its size before first boot without a wipe.
rm "${AVD_HOME}/docker-test-avd.avd/userdata-qemu.img"
sed -i 's/disk.dataPartition.size=10G/disk.dataPartition.size=2G/' "${AVD_HOME}/docker-test-avd.avd/config.ini"
sed '/EMULATOR_ALLOW_DATA_WIPE=/d' "$PROFILE_PATH" > "$TMP_DIR/fresh.profile"
HOME="$HOME_DIR" EMULATOR_ARGS_LOG="$EMULATOR_ARGS_LOG" EMULATOR_ENV_LOG="$EMULATOR_ENV_LOG" \
    EMULATOR_CONFIG_LOG="$EMULATOR_CONFIG_LOG" ADB_ARGS_LOG="$ADB_ARGS_LOG" \
    bash "${PLUGIN_DIR}/scripts/start-avd.sh" "$TMP_DIR/fresh.profile" > "$START_AVD_OUT" 2> "$START_AVD_ERR"
! grep -q -- -wipe-data "$EMULATOR_ARGS_LOG"

HOME="$HOME_DIR" EMULATOR_ARGS_LOG="$EMULATOR_ARGS_LOG" EMULATOR_ENV_LOG="$EMULATOR_ENV_LOG" \
    EMULATOR_CONFIG_LOG="$EMULATOR_CONFIG_LOG" ADB_ARGS_LOG="$ADB_ARGS_LOG" \
    FAKE_EMULATOR_HOLD=1 FAKE_EMULATOR_PID="$TMP_DIR/held.pid" \
    bash "${PLUGIN_DIR}/scripts/start-avd.sh" "$PROFILE_PATH" > "$START_AVD_OUT" 2> "$START_AVD_ERR" &
holding_driver=$!
for ((attempt=0; attempt<100; attempt++)); do [ ! -f "$TMP_DIR/held.pid" ] || break; sleep 0.05; done
[ -f "$TMP_DIR/held.pid" ]
if HOME="$HOME_DIR" bash "${PLUGIN_DIR}/scripts/start-avd.sh" "$PROFILE_PATH" > "$TMP_DIR/contender.log" 2>&1; then
    echo 'FAIL: competing start accepted' >&2; exit 1
fi
grep -q 'guard is busy' "$TMP_DIR/contender.log"
kill -TERM "$holding_driver"
status=0; wait "$holding_driver" || status=$?
holding_driver=
[ "$status" = 143 ]
[ ! -e "${AVD_HOME}/docker-test-avd.avd/config.ini.profile-start.guard" ]
! kill -0 "$(cat "$TMP_DIR/held.pid")" 2>/dev/null
[ ! -e "$ADB_ARGS_LOG" ]

echo "start-avd.sh fake-command smoke test passed."
