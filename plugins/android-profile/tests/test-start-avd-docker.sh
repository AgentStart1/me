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
    "${SDK_HOME}/cmdline-tools/latest/bin" \
    "${SDK_HOME}/emulator" \
    "${SDK_HOME}/platform-tools"
touch "${AVD_HOME}/docker-test-avd.avd/stale.lock"
cat > "${AVD_HOME}/docker-test-avd.avd/config.ini" <<'CONFIG'
hw.gpu.enabled=no
hw.gpu.mode=auto
hw.accelerometer_uncalibrated=yes
duplicate.key=old-first
duplicate.key=old-second
CONFIG

cat > "${SDK_HOME}/emulator/emulator" <<'EMULATOR'
#!/usr/bin/env bash
set -euo pipefail
printf "%s\n" "$@" > "${EMULATOR_ARGS_LOG}"
printf "DISPLAY=%s\n" "${DISPLAY:-}" > "${EMULATOR_ENV_LOG}"
cp "${ANDROID_AVD_HOME}/docker-test-avd.avd/config.ini" "${EMULATOR_CONFIG_LOG}"
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
    printf '%s\n' 'Name: docker-test-avd'
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

if [ -e "${AVD_HOME}/docker-test-avd.avd/stale.lock" ]; then
    echo "Error: stale AVD lock file was not removed." >&2
    exit 1
fi

echo "start-avd.sh fake-command smoke test passed."
