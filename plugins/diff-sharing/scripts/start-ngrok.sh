#!/usr/bin/env bash
set -euo pipefail

get_cache_dir() {
    local project_hash
    project_hash=$(printf '%s' "$PWD" | md5sum | cut -d' ' -f1)
    printf '%s\n' "${HOME}/.cache/diff-reports/${project_hash}"
}
OUTPUT_DIR="${REPORT_OUTPUT_DIR:-$(get_cache_dir)}"
PORT="${NGROK_PORT:-8080}"
PYTHON_COMMAND="${PYTHON_COMMAND:-}"
LOCAL_ONLY=false

find_python() {
    local candidate
    local -a candidates=(python3 python)
    [ -z "$PYTHON_COMMAND" ] || candidates=("$PYTHON_COMMAND")
    for candidate in "${candidates[@]}"; do
        if command -v "$candidate" >/dev/null 2>&1 &&
            "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info.major >= 3 else 1)' >/dev/null 2>&1; then
            printf '%s\n' "$candidate"; return 0
        fi
    done
    echo 'Error: No working Python 3 interpreter; set PYTHON_COMMAND.' >&2
    return 1
}

while [ $# -gt 0 ]; do
    case "$1" in
        --port|--output-dir)
            [ $# -ge 2 ] && [ -n "$2" ] || { echo "Error: $1 requires a value." >&2; exit 2; }
            case "$1" in --port) PORT="$2";; --output-dir) OUTPUT_DIR="$2";; esac
            shift 2;;
        --local-only) LOCAL_ONLY=true; shift;;
        --help|-h)
            echo 'Usage: start-ngrok.sh [--port PORT] [--output-dir DIR] [--local-only]'
            echo 'Serves the report on loopback; uses ngrok when available, otherwise stays local.'
            echo 'Defaults: NGROK_PORT=8080, REPORT_OUTPUT_DIR=~/.cache/diff-reports/<project-hash>.'
            echo 'PYTHON_COMMAND selects Python 3; NGROK_AUTHTOKEN or saved ngrok credentials enable a tunnel.'
            exit 0;;
        *) echo "Unknown option: $1" >&2; exit 2;;
    esac
done
[[ "$PORT" =~ ^[1-9][0-9]{0,4}$ ]] && [ "$PORT" -le 65535 ] || {
    echo 'Error: Port must be an integer from 1 to 65535.' >&2; exit 2;
}
[ -f "$OUTPUT_DIR/index.html" ] || {
    echo "Error: Report site missing; run generate-diff-site.sh first." >&2; exit 1;
}
PYTHON_EXECUTABLE="$(find_python)"
HTTP_PID=
TUNNEL_PID=
cleanup() {
    local status=$?
    trap - EXIT INT TERM
    local child
    for child in "$TUNNEL_PID" "$HTTP_PID"; do
        [ -n "$child" ] || continue
        if jobs -pr | grep -qx "$child"; then kill "$child" 2>/dev/null || true; fi
        wait "$child" 2>/dev/null || true
    done
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
"$PYTHON_EXECUTABLE" -m http.server "$PORT" --bind 127.0.0.1 --directory "$OUTPUT_DIR" &
HTTP_PID=$!
sleep 1
kill -0 "$HTTP_PID" 2>/dev/null || { echo 'Error: Report server failed to start.' >&2; exit 1; }
echo "Local report: http://127.0.0.1:$PORT"
echo 'Press Ctrl+C to stop this report server.'
if [ "$LOCAL_ONLY" = false ] && command -v ngrok >/dev/null 2>&1; then
    # The agent may use saved credentials. Never print tokens or claim anonymous access.
    ngrok http "http://127.0.0.1:$PORT" --log=stdout &
    TUNNEL_PID=$!
    if wait "$TUNNEL_PID"; then exit 0; fi
    TUNNEL_PID=
    echo 'ngrok could not start; the loopback report remains available.' >&2
elif [ "$LOCAL_ONLY" = false ]; then
    echo 'ngrok is unavailable; the loopback report remains available.' >&2
fi
wait "$HTTP_PID"
