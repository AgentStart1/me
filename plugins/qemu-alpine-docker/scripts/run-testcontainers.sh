#!/bin/bash
# Run a host test command against Docker inside the QEMU guest.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=vm-utils.sh
source "${SCRIPT_DIR}/vm-utils.sh"

PROFILE_ARG=""
VERBOSE=false
while [ $# -gt 0 ]; do
    case "$1" in
        --profile) shift; PROFILE_ARG="${1:-}"; shift ;;
        --profile=*) PROFILE_ARG="${1#*=}"; shift ;;
        --verbose|-v) VERBOSE=true; shift ;;
        --) shift; break ;;
        *) break ;;
    esac
done

if [ $# -eq 0 ]; then
    echo "Error: No test command provided." >&2
    echo "Usage: $0 [--profile <path>] [--verbose] -- <command> [args...]" >&2
    exit 1
fi

load_profile "${PROFILE_ARG:-${PLUGIN_DIR}/profiles/dev.profile}"
for key in VM_NAME SSH_PORT DOCKER_DAEMON_PORT TESTCONTAINERS_PORT_START TESTCONTAINERS_PORT_END; do
    require_profile_value "$key"
done
validate_port_range "$TESTCONTAINERS_PORT_START" "$TESTCONTAINERS_PORT_END"
TESTCONTAINERS_PULL_PAUSE_TIMEOUT_VALUE="${TESTCONTAINERS_PULL_PAUSE_TIMEOUT:-300}"
TESTCONTAINERS_PULL_TIMEOUT_VALUE="${TESTCONTAINERS_PULL_TIMEOUT:-1800}"
TESTCONTAINERS_RESOURCE_METRICS_VALUE="${TESTCONTAINERS_RESOURCE_METRICS:-true}"
TESTCONTAINERS_RESOURCE_METRICS_INTERVAL_VALUE="${TESTCONTAINERS_RESOURCE_METRICS_INTERVAL:-1}"
for timeout_key in TESTCONTAINERS_PULL_PAUSE_TIMEOUT_VALUE TESTCONTAINERS_PULL_TIMEOUT_VALUE; do
    timeout_value="${!timeout_key}"
    if [[ ! "$timeout_value" =~ ^[1-9][0-9]*$ ]]; then
        echo "Error: ${timeout_key%_VALUE} must be a positive integer (got '${timeout_value}')." >&2
        exit 1
    fi
done
case "$TESTCONTAINERS_RESOURCE_METRICS_VALUE" in
    true|false) ;;
    *)
        echo "Error: TESTCONTAINERS_RESOURCE_METRICS must be true or false (got '${TESTCONTAINERS_RESOURCE_METRICS_VALUE}')." >&2
        exit 1
        ;;
esac
if [[ ! "$TESTCONTAINERS_RESOURCE_METRICS_INTERVAL_VALUE" =~ ^[1-9][0-9]*$ ]] || \
   [ "$TESTCONTAINERS_RESOURCE_METRICS_INTERVAL_VALUE" -gt 60 ]; then
    echo "Error: TESTCONTAINERS_RESOURCE_METRICS_INTERVAL must be an integer from 1 to 60 (got '${TESTCONTAINERS_RESOURCE_METRICS_INTERVAL_VALUE}')." >&2
    exit 1
fi

if ! vm_is_running; then
    echo "Error: VM '${VM_NAME}' is not running. Start it first." >&2
    exit 1
fi
wait_for_docker_api 30

DOCKER_HOST_VALUE="tcp://127.0.0.1:${DOCKER_DAEMON_PORT}"
unset DOCKER_TLS_VERIFY DOCKER_CERT_PATH DOCKER_SOCKET
# Ryuk runs inside the guest and cleans test resources through the mounted guest socket.
unset TESTCONTAINERS_RYUK_DISABLED

COMMAND_ENV=(
    "DOCKER_HOST=${DOCKER_HOST_VALUE}"
    "TESTCONTAINERS_HOST_OVERRIDE=127.0.0.1"
    "TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock"
    "TESTCONTAINERS_PULL_PAUSE_TIMEOUT=${TESTCONTAINERS_PULL_PAUSE_TIMEOUT_VALUE}"
    "TESTCONTAINERS_PULL_TIMEOUT=${TESTCONTAINERS_PULL_TIMEOUT_VALUE}"
)
if is_windows; then
    WINDOWS_TEMP="${LOCALAPPDATA:-${USERPROFILE:-}}"
    [ -n "$WINDOWS_TEMP" ] || { echo "Error: Windows user profile path is unavailable." >&2; exit 1; }
    if [ -n "${LOCALAPPDATA:-}" ]; then
        WINDOWS_TEMP="${WINDOWS_TEMP}\\Temp"
    else
        WINDOWS_TEMP="${WINDOWS_TEMP}\\AppData\\Local\\Temp"
    fi
    command -v cygpath >/dev/null 2>&1 && WINDOWS_TEMP="$(cygpath -m "$WINDOWS_TEMP")"
    SOCKET_ENV_EXCLUSION="${MSYS2_ENV_CONV_EXCL:-}"
    [ -z "$SOCKET_ENV_EXCLUSION" ] || SOCKET_ENV_EXCLUSION+=";"
    SOCKET_ENV_EXCLUSION+="TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE"
    COMMAND_ENV+=(
        "TEMP=${WINDOWS_TEMP}"
        "TMP=${WINDOWS_TEMP}"
        "MSYS2_ENV_CONV_EXCL=${SOCKET_ENV_EXCLUSION}"
    )
fi

if [ "$VERBOSE" = "true" ]; then
    echo "DOCKER_HOST=${DOCKER_HOST_VALUE}" >&2
    echo "TESTCONTAINERS_HOST_OVERRIDE=127.0.0.1" >&2
    echo "Published port range=${TESTCONTAINERS_PORT_START}-${TESTCONTAINERS_PORT_END}" >&2
    echo "Image pull pause timeout=${TESTCONTAINERS_PULL_PAUSE_TIMEOUT_VALUE}s" >&2
    echo "Image pull timeout=${TESTCONTAINERS_PULL_TIMEOUT_VALUE}s" >&2
    echo "Resource metrics=${TESTCONTAINERS_RESOURCE_METRICS_VALUE} (interval ${TESTCONTAINERS_RESOURCE_METRICS_INTERVAL_VALUE}s)" >&2
    echo "Ryuk=enabled" >&2
fi

echo "Running Testcontainers command: $*" >&2
# Explicit env assignments survive the MSYS-to-native Windows process boundary;
# variables exported only by the parent Bash process may be omitted by Gradle test workers.
if [ "$TESTCONTAINERS_RESOURCE_METRICS_VALUE" = "false" ]; then
    exec env "${COMMAND_ENV[@]}" "$@"
fi

is_windows || {
    echo "Error: Automatic resource metrics require Windows PowerShell; set TESTCONTAINERS_RESOURCE_METRICS=false on other hosts." >&2
    exit 1
}
POWERSHELL_BIN="$(command -v powershell.exe || true)"
[ -n "$POWERSHELL_BIN" ] || {
    echo "Error: powershell.exe is required for automatic resource metrics." >&2
    exit 1
}

METRICS_SCRIPT_NATIVE="$(qemu_native_path "${SCRIPT_DIR}/collect-resource-metrics.ps1")"
METRICS_STOP_FILE="${RUN_DIR}/testcontainers-metrics-${BASHPID:-$$}.stop"
METRICS_REPORT="${VM_BASE_DIR}/metrics/latest.json"
METRICS_STOP_FILE_NATIVE="$(qemu_native_path "$METRICS_STOP_FILE")"
METRICS_REPORT_NATIVE="$(qemu_native_path "$METRICS_REPORT")"
SSH_KEY_NATIVE="$(qemu_native_path "$SSH_KEY")"
mkdir -p "$RUN_DIR" "$(dirname "$METRICS_REPORT")"
rm -f "$METRICS_STOP_FILE"

"$POWERSHELL_BIN" -NoProfile -NonInteractive -ExecutionPolicy Bypass \
    -File "$METRICS_SCRIPT_NATIVE" \
    -VmName "$VM_NAME" \
    -SshPort "$SSH_PORT" \
    -SshKeyPath "$SSH_KEY_NATIVE" \
    -StopFile "$METRICS_STOP_FILE_NATIVE" \
    -ReportPath "$METRICS_REPORT_NATIVE" \
    -IntervalSeconds "$TESTCONTAINERS_RESOURCE_METRICS_INTERVAL_VALUE" &
METRICS_PID=$!
COMMAND_STARTED_SECONDS=$SECONDS

finish_resource_metrics() {
    local command_status=$? duration_seconds=$((SECONDS - COMMAND_STARTED_SECONDS))
    trap - EXIT INT TERM
    printf '%s %s\n' "$command_status" "$duration_seconds" > "$METRICS_STOP_FILE"
    if ! wait "$METRICS_PID"; then
        echo "Warning: Resource metrics collection failed; test exit code remains ${command_status}." >&2
    fi
    rm -f "$METRICS_STOP_FILE"
    exit "$command_status"
}
trap finish_resource_metrics EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

env "${COMMAND_ENV[@]}" "$@"
