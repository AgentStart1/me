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
        local resolved_end
        resolved_end="$(default_testcontainers_port_end)" || return 1
        export TESTCONTAINERS_PORT_END="$resolved_end"
    fi
}

default_testcontainers_port_end() {
    local start="${TESTCONTAINERS_PORT_START:-20000}"
    validate_port "$start" TESTCONTAINERS_PORT_START || return 1
    [ "$start" -le 65408 ] || {
        echo 'Error: The automatic 128-port pool would exceed port 65535; choose explicit bounds.' >&2
        return 1
    }
    echo $((start + 127))
}

# Prefer Alpine's ordinary outbound range; large custom pools may require
# selecting the larger disjoint part of the unprivileged port space instead.
guest_outbound_port_range() {
    local start="${1:-$TESTCONTAINERS_PORT_START}" end="${2:-$TESTCONTAINERS_PORT_END}"
    local low high left right
    for bounds in '32768 60999' '1024 65535'; do
        read -r low high <<< "$bounds"
        if [ "$end" -lt "$low" ] || [ "$start" -gt "$high" ]; then
            echo "$low $high"; return 0
        fi
        left=$((start > low ? start - low : 0))
        right=$((end < high ? high - end : 0))
        if [ "$left" -gt 0 ] || [ "$right" -gt 0 ]; then
            if [ "$left" -ge "$right" ]; then echo "$low $((start - 1))"
            else echo "$((end + 1)) $high"; fi
            return 0
        fi
    done
    echo 'Error: Publish pool leaves no unprivileged guest outbound ports.' >&2
    return 1
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
    [ "$start" -ge 1024 ] || {
        echo "Error: Docker publish pool must start at 1024 or above (guest kernel ephemeral range)." >&2
        return 1
    }
    guest_outbound_port_range "$start" "$end" >/dev/null
}

validate_image_reference() {
    local image="$1"
    [[ "$image" =~ ^[A-Za-z0-9._/:@-]+$ ]] || {
        echo "Error: Invalid container image reference '${image}'." >&2
        return 1
    }
}
