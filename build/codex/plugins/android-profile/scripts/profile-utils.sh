#!/bin/bash

set -euo pipefail

declare -gA PROFILE_LOADED_KEYS=()

trim_whitespace() {
    local value="$1"

    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"

    printf '%s' "$value"
}

load_profile() {
    local profile_path="$1"
    local line_number=0
    local raw_line trimmed_line key raw_value parsed_value

    if [ ! -f "$profile_path" ]; then
        echo "Error: profile not found: $profile_path" >&2
        return 1
    fi

    while IFS= read -r raw_line || [ -n "$raw_line" ]; do
        line_number=$((line_number + 1))
        trimmed_line=$(trim_whitespace "$raw_line")

        if [ -z "$trimmed_line" ] || [[ "$trimmed_line" == \#* ]]; then
            continue
        fi

        if [[ ! "$trimmed_line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
            echo "Error: invalid profile line ${line_number} in ${profile_path}: ${raw_line}" >&2
            return 1
        fi

        key="${trimmed_line%%=*}"
        raw_value="${trimmed_line#*=}"

        if [[ "$raw_value" == *'$('* ]] || [[ "$raw_value" == *'`'* ]] || [[ "$raw_value" == *'$'* ]]; then
            echo "Error: shell expansion is not allowed in ${profile_path}:${line_number}" >&2
            return 1
        fi

        parsed_value=""
        eval "parsed_value=${raw_value}"
        printf -v "$key" '%s' "$parsed_value"
        export "$key"
        PROFILE_LOADED_KEYS["$profile_path:$key"]=1
    done < "$profile_path"
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
    local name="$1"
    local candidate
    local tool_dir=""
    local android_home="${ANDROID_HOME:-${HOME}/android-sdk}"

    for candidate in "$name" "${name}.bat" "${name}.cmd" "${name}.exe"; do
        if command -v "$candidate" >/dev/null 2>&1; then
            command -v "$candidate"
            return 0
        fi
    done

    if [ -n "$android_home" ]; then
        case "$name" in
            sdkmanager|avdmanager)
                tool_dir="$android_home/cmdline-tools/latest/bin"
                ;;
            adb)
                tool_dir="$android_home/platform-tools"
                ;;
            emulator)
                tool_dir="$android_home/emulator"
                ;;
            *)
                tool_dir=""
                ;;
        esac

        if resolve_executable_in_dir "$tool_dir" "$name"; then
            return 0
        fi
    fi

    echo "Error: Android tool not found: ${name}. Add it to PATH or set ANDROID_HOME." >&2
    return 1
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
    local prefix="$2"
    local dash="$3"
    shift 3
    local -a excludes=("$@")

    local -a flag_vars value_vars
    local var name_raw name value should_skip

    mapfile -t flag_vars < <(compgen -A variable "${prefix}_FLAG_")
    for var in "${flag_vars[@]}"; do
        name_raw="${var#${prefix}_FLAG_}"
        should_skip=false
        for name in "${excludes[@]}"; do
            if [ "$name_raw" = "$name" ]; then
                should_skip=true
                break
            fi
        done
        if [ "$should_skip" = true ]; then
            continue
        fi

        value="${!var-}"
        if is_true "$value"; then
            name="${name_raw//_/-}"
            target_ref+=("${dash}${name}")
        fi
    done

    mapfile -t value_vars < <(compgen -A variable "${prefix}_VALUE_")
    for var in "${value_vars[@]}"; do
        name_raw="${var#${prefix}_VALUE_}"
        should_skip=false
        for name in "${excludes[@]}"; do
            if [ "$name_raw" = "$name" ]; then
                should_skip=true
                break
            fi
        done
        if [ "$should_skip" = true ]; then
            continue
        fi

        value="${!var-}"
        if [ -n "$value" ]; then
            name="${name_raw//_/-}"
            target_ref+=("${dash}${name}" "$value")
        fi
    done
}

resolve_avd_config_path() {
    local avd_name="$1"
    local avd_home
    local avd_ini=""
    local avd_dir=""

    avd_home="$(resolve_android_avd_home)"
    avd_ini="${avd_home}/${avd_name}.ini"

    if [ -n "${AVDMANAGER_VALUE_path:-}" ]; then
        avd_dir="$AVDMANAGER_VALUE_path"
    elif [ -f "$avd_ini" ]; then
        avd_dir="$(awk -F= '$1 == "path" { print substr($0, index($0, "=") + 1); exit }' "$avd_ini")"
    fi

    if [ -z "$avd_dir" ]; then
        avd_dir="${avd_home}/${avd_name}.avd"
    fi

    printf '%s\n' "${avd_dir}/config.ini"
}

read_emulator_config_value() {
    local config_path="$1"
    local target_key="$2"

    if [ ! -f "$config_path" ]; then
        return 1
    fi

    TARGET_KEY="$target_key" awk -F= '
        $1 == ENVIRON["TARGET_KEY"] {
            print substr($0, index($0, "=") + 1)
            found = 1
            exit
        }
        END {
            exit found ? 0 : 1
        }
    ' "$config_path"
}

apply_emulator_config() {
    local config_path="$1"
    local -a config_vars
    local var key value temp_path

    mapfile -t config_vars < <(compgen -A variable EMULATOR_CONFIG_)
    if [ "${#config_vars[@]}" -eq 0 ]; then
        return 0
    fi

    if [ ! -f "$config_path" ]; then
        echo "Error: emulator config file not found: $config_path" >&2
        return 1
    fi
    if [ ! -w "$config_path" ]; then
        echo "Error: emulator config file is not writable: $config_path" >&2
        return 1
    fi

    echo "Applying emulator config overrides: $config_path"

    for var in "${config_vars[@]}"; do
        key="${var#EMULATOR_CONFIG_}"
        key="${key//__/.}"
        value="${!var-}"
        temp_path="$(mktemp "${config_path}.tmp.XXXXXX")"

        TARGET_KEY="$key" TARGET_VALUE="$value" awk '
            BEGIN {
                target_key = ENVIRON["TARGET_KEY"]
                target_value = ENVIRON["TARGET_VALUE"]
                replaced = 0
            }
            {
                separator = index($0, "=")
                current_key = separator ? substr($0, 1, separator - 1) : ""
                if (current_key == target_key) {
                    if (!replaced) {
                        print target_key "=" target_value
                        replaced = 1
                    }
                    next
                }
                print
            }
            END {
                if (!replaced) {
                    print target_key "=" target_value
                }
            }
        ' "$config_path" > "$temp_path"
        chmod --reference="$config_path" "$temp_path"
        mv "$temp_path" "$config_path"
    done
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
