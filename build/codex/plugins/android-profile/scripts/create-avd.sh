#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOME_DIR="${HOME:-/home/$(id -un)}"
PROFILE_DIR="${ANDROID_PROFILE_DIR:-${HOME_DIR}/android-profiles}"
ANDROID_PROFILE_ARG="${1:-}"
if [ -n "$ANDROID_PROFILE_ARG" ]; then
    ANDROID_PROFILE="$ANDROID_PROFILE_ARG"
else
    ANDROID_PROFILE="${ANDROID_PROFILE:-${PROFILE_DIR}/mobile.profile}"
fi

# shellcheck source=/dev/null
source "${SCRIPT_DIR}/profile-utils.sh"

validate_system_image_arch() {
    local arch="$1"
    local expected_abi=""

    case "$arch" in
        x86_64)
            expected_abi="x86_64"
            ;;
        aarch64)
            expected_abi="arm64-v8a"
            ;;
        *)
            echo "Warning: Unknown architecture $arch. Skipping SYS_IMG_PKG ABI validation." >&2
            return 0
            ;;
    esac

    if [[ "$SYS_IMG_PKG" == *";x86_64" ]] || [[ "$SYS_IMG_PKG" == *";arm64-v8a" ]] || [[ "$SYS_IMG_PKG" == *";armeabi-v7a" ]]; then
        echo "Error: SYS_IMG_PKG in profile must not include an ABI suffix; use the package prefix only: ${SYS_IMG_PKG}" >&2
        return 1
    fi

    RESOLVED_SYS_IMG_PKG="${SYS_IMG_PKG};${expected_abi}"
}

build_avdmanager_args() {
    local -n args_ref="$1"

    args_ref=(
        create
        avd
        --name "$AVD_NAME"
        --package "$RESOLVED_SYS_IMG_PKG"
    )

    append_args_from_env args_ref AVDMANAGER -- name package
}

is_sdk_package_installed() {
    local package="$1"
    local installed_packages

    if ! installed_packages="$("$SDKMANAGER" --list_installed 2>/dev/null)"; then
        echo "Warning: Failed to query installed SDK packages. Will attempt to install ${package}." >&2
        return 1
    fi

    printf '%s\n' "$installed_packages" \
        | awk -v package="$package" -F '|' '
            {
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", $1)
                if ($1 == package) {
                    found = 1
                }
            }
            END {
                exit found ? 0 : 1
            }
        '
}

install_system_image_if_needed() {
    local package="$1"

    echo "Checking whether system image is already installed: ${package}" >&2
    if is_sdk_package_installed "$package"; then
        echo "System image already installed. Skipping download: ${package}" >&2
        return 0
    fi

    echo "System image not found. Installing: ${package}" >&2
    "$SDKMANAGER" "$package"
    echo "System image installation finished: ${package}" >&2
}

load_profile "$ANDROID_PROFILE"
assert_profile_keys_absent "$ANDROID_PROFILE" ARCH ABI AVD_ARCH AVD_ABI AVDMANAGER_ABI AVDMANAGER_ARCH EMULATOR_ABI EMULATOR_ARCH
require_profile_value AVD_NAME
require_profile_value SYS_IMG_PKG

SDKMANAGER="$(resolve_android_tool sdkmanager)"
AVDMANAGER="$(resolve_android_tool avdmanager)"
"${SCRIPT_DIR}/accept-sdk-licenses.sh"

ARCH="$(uname -m)"
echo "Detected architecture: $ARCH" >&2
validate_system_image_arch "$ARCH"

echo "AVD_NAME: $AVD_NAME" >&2
echo "System image package prefix: $SYS_IMG_PKG" >&2
echo "Resolved system image package: $RESOLVED_SYS_IMG_PKG" >&2
install_system_image_if_needed "$RESOLVED_SYS_IMG_PKG"

if ! "$AVDMANAGER" list avd | grep -q "Name: $AVD_NAME"; then
    declare -a avdmanager_args

    echo "Creating AVD: $AVD_NAME" >&2
    build_avdmanager_args avdmanager_args
    echo "avdmanager command: avdmanager ${avdmanager_args[*]}" >&2

    "$AVDMANAGER" "${avdmanager_args[@]}"
else
    echo "AVD '$AVD_NAME' already exists." >&2
fi
