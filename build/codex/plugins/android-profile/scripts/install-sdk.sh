#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=/dev/null
source "${SCRIPT_DIR}/profile-utils.sh"

ANDROID_HOME="${ANDROID_HOME:-${HOME}/android-sdk}"
echo "android home: $ANDROID_HOME"
export ANDROID_HOME
CLI_VERSION=""

version_lt() {
    [ "$1" = "$2" ] && return 1
    local IFS=.
    local i ver1=($1) ver2=($2)
    for ((i=${#ver1[@]}; i<${#ver2[@]}; i++)); do ver1[i]=0; done
    for ((i=0; i<${#ver1[@]}; i++)); do
        if [[ -z ${ver2[i]} ]]; then ver2[i]=0; fi
        if ((10#${ver1[i]} < 10#${ver2[i]})); then return 0; fi
        if ((10#${ver1[i]} > 10#${ver2[i]})); then return 1; fi
    done
    return 1
}

platform_tag() {
    case "$(uname -s 2>/dev/null)" in
        MINGW*|MSYS*|CYGWIN*)
            printf '%s\n' win
            ;;
        Darwin*)
            printf '%s\n' mac
            ;;
        *)
            printf '%s\n' linux
            ;;
    esac
}

download_file() {
    local url="$1"
    local output="$2"

    if command -v curl >/dev/null 2>&1; then
        curl -fL "$url" -o "$output"
    elif command -v wget >/dev/null 2>&1; then
        wget -O "$output" "$url"
    else
        echo "Error: curl or wget is required to download Android SDK command-line tools." >&2
        return 1
    fi
}

maybe_chown_android_home() {
    if is_windows_shell; then
        return 0
    fi

    if command -v sudo >/dev/null 2>&1; then
        sudo chown -R "$(whoami):$(whoami)" "$ANDROID_HOME"
    fi
}

resolve_sdkmanager_in_dir() {
    local dir="$1"

    resolve_executable_in_dir "$dir" sdkmanager
}

mkdir -p "$ANDROID_HOME"
maybe_chown_android_home

download_and_install_cmdline_tools() {
    echo "Android SDK command-line tools not found or outdated. Downloading..."

    local os_tag
    local download_url
    os_tag="$(platform_tag)"
    download_url="https://dl.google.com/android/repository/commandlinetools-${os_tag}-14742923_latest.zip"

    if ! download_file "$download_url" commandline-tools.zip; then
        echo "Error: Failed to download command-line tools from $download_url"
        return 1
    fi

    mkdir -p "${ANDROID_HOME}/cmdline-tools"
    if ! unzip -q commandline-tools.zip -d "${ANDROID_HOME}/cmdline-tools"; then
        echo "Error: Failed to extract command-line tools"
        rm -f commandline-tools.zip
        return 1
    fi

    rm -rf "${ANDROID_HOME}/cmdline-tools/latest"
    mv "${ANDROID_HOME}/cmdline-tools/cmdline-tools" "${ANDROID_HOME}/cmdline-tools/latest"
    rm -f commandline-tools.zip
    echo "Android SDK command-line tools installed."
}

if [ ! -d "${ANDROID_HOME}/cmdline-tools/latest" ]; then
    echo "Android SDK command-line tools not found. Installing..."
    download_and_install_cmdline_tools || exit 1
else
    echo "Android SDK command-line tools found."

    CLI_VERSION=$(grep "Pkg.Revision" "${ANDROID_HOME}/cmdline-tools/latest/source.properties" 2>/dev/null | awk -F '=' '{print $2}')
    echo "Current command line tools version: ${CLI_VERSION:-unknown}"
    if [ -n "$CLI_VERSION" ] && version_lt "$CLI_VERSION" "20.0"; then
        echo "Updating command line tools to the latest version..."
        download_and_install_cmdline_tools || exit 1
    fi
fi

SDKMANAGER="$(resolve_android_tool sdkmanager)"

"${SCRIPT_DIR}/accept-sdk-licenses.sh"

if [ ! -d "${ANDROID_HOME}/platform-tools" ]; then
    echo "Installing platform-tools..."
    "$SDKMANAGER" "platform-tools"
else
    echo "platform-tools already installed."
fi

if [ ! -d "${ANDROID_HOME}/emulator" ]; then
    echo "Installing emulator..."
    "$SDKMANAGER" "emulator"
else
    echo "emulator already installed."
fi

echo "Android SDK setup is complete."
