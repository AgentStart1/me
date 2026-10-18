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

declare -gA PROFILE_VALUES=()

load_profile() {
    local profile_path="$1" temporary key value
    PROFILE_VALUES=()
    temporary="$(mktemp)"
    if ! profile_python profile "$profile_path" > "$temporary"; then rm -f "$temporary"; return 1; fi
    while IFS= read -r -d '' key && IFS= read -r -d '' value; do
        PROFILE_VALUES["$key"]="$value"
    done < "$temporary"
    rm -f "$temporary"
}

require_profile_value() {
    local key="$1"
    local value="${PROFILE_VALUES[$key]-}"

    if [ -z "$value" ]; then
        echo "Error: required profile key $key is missing or empty." >&2
        return 1
    fi
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
    profile_python tool "$1" "${PROFILE_VALUES[ANDROID_HOME]:-${ANDROID_HOME:-}}"
}

append_args_from_profile() {
    local -n target_ref="$1"
    local prefix="$2" dash="$3" var temporary
    shift 3
    local -a assignments=()
    for var in "${!PROFILE_VALUES[@]}"; do
        case "$var" in "${prefix}_FLAG_"*|"${prefix}_VALUE_"*) assignments+=("$var=${PROFILE_VALUES[$var]}");; esac
    done
    temporary="$(mktemp)"
    if ! profile_python args "$prefix" -- "$dash" "$@" @@ "${assignments[@]}" > "$temporary"; then
        rm -f "$temporary"; return 1
    fi
    while IFS= read -r -d '' var; do target_ref+=("$var"); done < "$temporary"
    rm -f "$temporary"
}

assert_profile_keys_absent() {
    local profile_path="$1"
    shift

    local key
    for key in "$@"; do
        if [ -n "${PROFILE_VALUES[$key]+x}" ]; then
            echo "Error: profile ${profile_path} must not define ${key}; architecture is detected dynamically." >&2
            return 1
        fi
    done
}
