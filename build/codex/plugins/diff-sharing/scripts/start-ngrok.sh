#!/usr/bin/env bash
set -euo pipefail

# start-ngrok.sh
# Starts an ngrok tunnel to expose the report site
#
# Usage: start-ngrok.sh [--port PORT] [--output-dir DIR]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"

# Generate cache directory based on project path hash
get_cache_dir() {
    local project_dir="${1:-$PWD}"
    local project_hash
    project_hash=$(echo -n "$project_dir" | md5sum | cut -d' ' -f1)
    echo "${HOME}/.cache/diff-reports/${project_hash}"
}

# Default configuration
OUTPUT_DIR="${REPORT_OUTPUT_DIR:-$(get_cache_dir)}"
PORT="${NGROK_PORT:-8080}"
NGROK_AUTHTOKEN="${NGROK_AUTHTOKEN:-}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --port)
            PORT="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [--port PORT] [--output-dir DIR]"
            echo ""
            echo "Starts an ngrok tunnel to expose the report site."
            echo ""
            echo "Options:"
            echo "  --port PORT         Local port to serve the report (default: 8080)"
            echo "  --output-dir DIR    Directory containing the report site (default: ./test-reports)"
            echo "  --help, -h          Show this help message"
            echo ""
            echo "Environment variables:"
            echo "  NGROK_AUTHTOKEN     ngrok authentication token (required for public tunnel)"
            echo "  NGROK_PORT          Local port to expose (default: 8080)"
            echo "  REPORT_OUTPUT_DIR   Directory containing the report site"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# Check if ngrok is installed
if ! command -v ngrok &> /dev/null; then
    echo "Error: ngrok is not installed" >&2
    echo ""
    echo "Please install ngrok:" >&2
    echo "  • macOS: brew install ngrok" >&2
    echo "  • Linux: snap install ngrok" >&2
    echo "  • Windows: choco install ngrok" >&2
    echo ""
    echo "Or download from: https://ngrok.com/download" >&2
    exit 1
fi

# Check if report site exists
if [[ ! -f "$OUTPUT_DIR/index.html" ]]; then
    echo "Error: Report site not found at $OUTPUT_DIR/index.html" >&2
    echo "Run generate-diff-site.sh first." >&2
    exit 1
fi

# Check for auth token
if [[ -z "$NGROK_AUTHTOKEN" ]]; then
    echo "Warning: NGROK_AUTHTOKEN not set" >&2
    echo "Using ngrok free tier with limited features." >&2
    echo "Set NGROK_AUTHTOKEN for full features and custom domains." >&2
    echo ""
fi

echo "Starting report server..."
echo "  Directory: $OUTPUT_DIR"
echo "  Port: $PORT"

# Start HTTP server in background
HTTP_PID=""
cleanup() {
    if [[ -n "$HTTP_PID" ]]; then
        echo ""
        echo "Stopping HTTP server (PID: $HTTP_PID)..."
        kill "$HTTP_PID" 2>/dev/null || true
        wait "$HTTP_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

cd "$OUTPUT_DIR"
python3 -m http.server "$PORT" &
HTTP_PID=$!
sleep 1

# Verify server is running
if ! kill -0 "$HTTP_PID" 2>/dev/null; then
    echo "Error: Failed to start HTTP server" >&2
    exit 1
fi

echo "HTTP server running on http://localhost:$PORT (PID: $HTTP_PID)"

# Start ngrok
echo ""
echo "Starting ngrok tunnel..."
echo "  Press Ctrl+C to stop"
echo ""

ngrok http "$PORT" --log=stdout
