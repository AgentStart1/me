#!/bin/bash

set -euo pipefail

PROFILE_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
profile_python() {
    local candidate
    local -a candidates=(python3 python)
    [ -z "${ANDROID_PROFILE_PYTHON:-}" ] || candidates=("$ANDROID_PROFILE_PYTHON")
    for candidate in "${candidates[@]}"; do
        if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
            "$candidate" "$PROFILE_SCRIPT_DIR/profile_controller.py" "$@"
            return $?
        fi
    done
    echo 'Error: Python 3.10+ is required; set ANDROID_PROFILE_PYTHON.' >&2
    return 1
}

declare -gA PROFILE_LOADED_KEYS=()

trim_whitespace() {
    local value="$1"

    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"

    printf '%s' "$value"
}

load_profile() {
    local profile_path="$1" temporary key value
    temporary="$(mktemp)"
    if ! profile_python profile "$profile_path" > "$temporary"; then rm -f "$temporary"; return 1; fi
    while IFS= read -r -d '' key && IFS= read -r -d '' value; do
        printf -v "$key" '%s' "$value"
        export "$key"
        PROFILE_LOADED_KEYS["$profile_path:$key"]=1
    done < "$temporary"
    rm -f "$temporary"
}

profile_has_key() {
    local profile_path="$1"
    local key="$2"

    [ -n "${PROFILE_LOADED_KEYS["$profile_path:$key"]+x}" ]
}

require_profile_value() {
    local key="$1"
    local value="${!key-}"

    if [ -z "$value" ]; then
        echo "Error: required profile key $key is missing or empty." >&2
        return 1
    fi
}

is_true() {
    case "${1:-}" in
        true|TRUE|yes|YES|1|on|ON)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

is_windows_shell() {
    case "$(uname -s 2>/dev/null)" in
        MINGW*|MSYS*|CYGWIN*)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

resolve_executable_in_dir() {
    local dir="$1"
    local name="$2"
    local candidate

    [ -n "$dir" ] || return 1

    for candidate in "$dir/$name" "$dir/${name}.bat" "$dir/${name}.cmd" "$dir/${name}.exe"; do
        if [ -f "$candidate" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    return 1
}

resolve_android_tool() {
    profile_python tool "$1"
}

resolve_android_avd_home() {
    local home_dir="${HOME:-/home/$(id -un)}"

    printf '%s\n' "${ANDROID_AVD_HOME:-${ANDROID_USER_HOME:-${home_dir}/.android}/avd}"
}

has_any_var_with_prefix() {
    local var_prefix="$1"
    local -a vars

    mapfile -t vars < <(compgen -A variable "$var_prefix")
    [ "${#vars[@]}" -gt 0 ]
}

append_args_from_env() {
    local -n target_ref="$1"
    local prefix="$2" dash="$3" var temporary
    shift 3
    local -a assignments=()
    while IFS= read -r var; do assignments+=("$var=${!var}"); done < <(compgen -A variable "${prefix}_FLAG_")
    while IFS= read -r var; do assignments+=("$var=${!var}"); done < <(compgen -A variable "${prefix}_VALUE_")
    temporary="$(mktemp)"
    if ! profile_python args "$prefix" -- "$dash" "$@" @@ "${assignments[@]}" > "$temporary"; then
        rm -f "$temporary"; return 1
    fi
    while IFS= read -r -d '' var; do target_ref+=("$var"); done < "$temporary"
    rm -f "$temporary"
}

resolve_avd_config_path() {
    profile_python config-path "$1" "${AVDMANAGER_VALUE_path:-}"
}

read_emulator_config_value() {
    profile_python read "$1" "$2"
}

apply_emulator_config() {
    local var
    local -a values=()
    while IFS= read -r var; do values+=("$var=${!var}"); done < <(compgen -A variable EMULATOR_CONFIG_)
    profile_python apply "$1" "${values[@]}"
}

assert_profile_keys_absent() {
    local profile_path="$1"
    shift

    local key
    for key in "$@"; do
        if profile_has_key "$profile_path" "$key"; then
            echo "Error: profile ${profile_path} must not define ${key}; architecture is detected dynamically." >&2
            return 1
        fi
    done
}
