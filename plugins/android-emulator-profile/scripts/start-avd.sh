#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOME_DIR="${HOME:-/home/$(id -un)}"
PROFILE_DIR="${ANDROID_PROFILE_DIR:-${HOME_DIR}/android-profiles}"
PROFILE_ARG="${1:-}"
if [ -n "$PROFILE_ARG" ]; then
    ANDROID_PROFILE="$PROFILE_ARG"
else
    ANDROID_PROFILE="${ANDROID_PROFILE:-${PROFILE_DIR}/mobile.profile}"
fi
LOADED_PROFILE="$ANDROID_PROFILE"

# shellcheck source=/dev/null
source "${SCRIPT_DIR}/profile-utils.sh"

build_emulator_args() {
    local -n args_ref="$1"

    args_ref=(-avd "$AVD_NAME")
    if [ "${WIPE_DATA_ON_START:-false}" = true ]; then
        args_ref+=("-wipe-data")
    fi
    append_args_from_env args_ref EMULATOR -
}

shutdown() {
    local status="$1"
    trap - SIGTERM SIGINT
    echo "Shutting down emulator gracefully..."
    if jobs -pr | grep -qx "$EMULATOR_PID"; then
        kill -TERM "$EMULATOR_PID" 2>/dev/null || true
        wait "$EMULATOR_PID" || true
    fi
    echo "Emulator shut down."
    exit "$status"
}

load_profile "$ANDROID_PROFILE"

assert_profile_keys_absent "$LOADED_PROFILE" ARCH ABI AVD_ARCH AVD_ABI AVDMANAGER_ABI AVDMANAGER_ARCH EMULATOR_ABI EMULATOR_ARCH
require_profile_value AVD_NAME

EMULATOR="$(resolve_android_tool emulator)"

AVD_CONFIG_PATH="$(resolve_avd_config_path "$AVD_NAME")"
START_GUARD="${AVD_CONFIG_PATH}.profile-start.guard"
mkdir "$START_GUARD" 2>/dev/null || {
    echo 'Error: AVD start guard is busy or its directory is unavailable; inspect the owning launch before recovery.' >&2
    exit 1
}
cleanup_start_guard() {
    local status=$?
    trap - EXIT
    rmdir "$START_GUARD" 2>/dev/null || status=1
    exit "$status"
}
trap cleanup_start_guard EXIT
EMULATOR_PID=
trap 'shutdown 143' SIGTERM
trap 'shutdown 130' SIGINT
if [ -n "$(find "$(dirname "$AVD_CONFIG_PATH")" -maxdepth 1 -name '*.lock' -print -quit)" ]; then
    echo 'Error: Existing AVD lock; confirm its emulator has stopped before manual recovery. Configuration was not changed.' >&2
    exit 1
fi
WIPE_DATA_ON_START=false
if [ -f "$AVD_CONFIG_PATH" ] && [ -n "${EMULATOR_CONFIG_disk__dataPartition__size:-}" ]; then
    CURRENT_DATA_PARTITION_SIZE="$(read_emulator_config_value "$AVD_CONFIG_PATH" "disk.dataPartition.size" || true)"
    if [ "$CURRENT_DATA_PARTITION_SIZE" != "$EMULATOR_CONFIG_disk__dataPartition__size" ]; then
        AVD_DATA_DIR="$(dirname "$AVD_CONFIG_PATH")"
        CUSTOM_DATA_PATH="$(read_emulator_config_value "$AVD_CONFIG_PATH" disk.dataPartition.path || true)"
        if [ -e "$AVD_DATA_DIR/userdata-qemu.img" ] || [ -e "$AVD_DATA_DIR/userdata-qemu.img.qcow2" ] ||
            [ -n "${EMULATOR_VALUE_data:-$CUSTOM_DATA_PATH}" ]; then
            is_true "${EMULATOR_ALLOW_DATA_WIPE:-false}" || {
                echo 'Error: Resizing existing AVD data requires a wipe. Preserve its data or explicitly set EMULATOR_ALLOW_DATA_WIPE=true in the profile.' >&2
                exit 1
            }
            WIPE_DATA_ON_START=true
            echo "AVD data partition size changed; emulator will start with the explicitly allowed -wipe-data."
        fi
    fi
fi
apply_emulator_config "$AVD_CONFIG_PATH"

echo "Starting emulator..."

if [ -n "${EMULATOR_DISPLAY:-}" ]; then export DISPLAY="$EMULATOR_DISPLAY"; fi
# Let the emulator own and validate its AVD locks. Never delete another
# instance's locks or send an unqualified adb shutdown to an unrelated device.

declare -a emulator_args
build_emulator_args emulator_args
echo "Emulator command: emulator ${emulator_args[*]}"

"$EMULATOR" "${emulator_args[@]}" &

EMULATOR_PID=$!

trap 'shutdown 143' SIGTERM
trap 'shutdown 130' SIGINT

wait "$EMULATOR_PID"
echo "Emulator process has exited."
