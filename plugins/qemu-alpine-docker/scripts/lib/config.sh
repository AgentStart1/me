# Profile and user-supplied value validation helpers.
# Sourced by ../vm-utils.sh before modules that consume validated settings.

load_profile() {
    local profile_path="${1:-}"
    if [ -z "$profile_path" ] || [ ! -f "$profile_path" ]; then
        echo "Error: Profile not found: ${profile_path:-<empty>}." >&2
        return 1
    fi
    local line
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line%$'\r'}"
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "${line//[[:space:]]/}" ]] && continue
        if [[ "$line" =~ \$[\(\{] ]] || [[ "$line" =~ \` ]]; then
            echo "Error: Profile contains shell expansion: ${line}" >&2
            return 1
        fi
        if [[ ! "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
            echo "Error: Invalid profile entry: ${line}" >&2
            return 1
        fi
        export "$line"
    done < "$profile_path"
    if [ -n "${VM_NAME:-}" ] && [[ ! "$VM_NAME" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
        echo 'Error: VM_NAME must be a simple directory name.' >&2
        return 1
    fi
    if [ "${TESTCONTAINERS_PORT_END:-}" = auto ]; then
        export TESTCONTAINERS_PORT_END="$(default_testcontainers_port_end)"
    fi
}

default_testcontainers_port_end() {
    if is_windows; then echo 20015; else echo 20255; fi
}

# Select the larger disjoint part of Alpine's ordinary outbound range when a
# custom publish pool overlaps it. The 512-port ceiling leaves ample space.
guest_outbound_port_range() {
    local start="$TESTCONTAINERS_PORT_START" end="$TESTCONTAINERS_PORT_END"
    if [ "$end" -lt 32768 ] || [ "$start" -gt 60999 ]; then
        echo '32768 60999'
    elif [ $((start - 32768)) -ge $((60999 - end)) ]; then
        echo "32768 $((start - 1))"
    else
        echo "$((end + 1)) 60999"
    fi
}

require_profile_value() {
    local key="$1"
    [ -n "${!key:-}" ] || {
        echo "Error: Required profile key '${key}' is not set." >&2
        return 1
    }
}

validate_port() {
    local port="$1" label="${2:-port}"
    if [[ ! "$port" =~ ^[1-9][0-9]{0,4}$ ]] || [ "$port" -lt 1 ] || [ "$port" -gt 65535 ]; then
        echo "Error: ${label} must be an integer from 1 to 65535 (got '${port}')." >&2
        return 1
    fi
}

validate_port_range() {
    local start="$1" end="$2"
    validate_port "$start" "TESTCONTAINERS_PORT_START" || return 1
    validate_port "$end" "TESTCONTAINERS_PORT_END" || return 1
    [ "$start" -le "$end" ] || {
        echo "Error: Testcontainers port range start must not exceed end." >&2
        return 1
    }
    [ $((end - start + 1)) -le 512 ] || {
        echo "Error: Testcontainers port range may contain at most 512 ports." >&2
        return 1
    }
}

validate_image_reference() {
    local image="$1"
    [[ "$image" =~ ^[A-Za-z0-9._/:@-]+$ ]] || {
        echo "Error: Invalid container image reference '${image}'." >&2
        return 1
    }
}
