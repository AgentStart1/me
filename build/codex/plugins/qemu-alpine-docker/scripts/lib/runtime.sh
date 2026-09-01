# Low-level platform, command, and process helpers.
# Sourced by ../vm-utils.sh after shared path variables are initialized.

platform_tag() {
    case "$(uname -s)" in
        Linux*) echo "linux" ;;
        Darwin*) echo "mac" ;;
        MINGW*|MSYS*|CYGWIN*) echo "win" ;;
        *) echo "unknown" ;;
    esac
}

is_windows() { [ "$(platform_tag)" = "win" ]; }

qemu_native_path() {
    local path="$1"
    if is_windows && command -v cygpath >/dev/null 2>&1; then
        cygpath -m "$path"
    else
        echo "$path"
    fi
}

require_command() {
    local cmd="$1" label="${2:-$1}"
    command -v "$cmd" >/dev/null 2>&1 || {
        echo "Error: ${label} ('${cmd}') is not installed or not on PATH." >&2
        return 1
    }
}

ensure_msys2_tools() {
    [ "${QEMU_ALPINE_SKIP_MSYS2_PATH:-0}" = "1" ] && return 0
    if is_windows; then
        local current_user dir
        current_user="$(id -un)"
        local candidates=(
            "/c/Users/${current_user}/msys2/ucrt64/bin"
            "/c/msys64/ucrt64/bin"
            "/c/Users/${current_user}/msys2/usr/bin"
            "/c/msys64/usr/bin"
            "/c/Windows/System32/OpenSSH"
        )
        for dir in "${candidates[@]}"; do
            if [ -d "$dir" ] && [[ ":$PATH:" != *":$dir:"* ]]; then
                export PATH="$dir:$PATH"
            fi
        done
    fi
}

process_is_running() {
    local pid="${1:-}"
    [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null
}

wait_for_process_exit() {
    local pid="$1" timeout="$2" elapsed=0
    while process_is_running "$pid" && [ "$elapsed" -lt "$timeout" ]; do
        sleep 1
        elapsed=$((elapsed + 1))
    done
    ! process_is_running "$pid"
}
