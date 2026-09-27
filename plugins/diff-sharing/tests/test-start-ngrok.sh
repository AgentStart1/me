#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

BIN_DIR="$WORK_DIR/bin"
OUTPUT_DIR="$WORK_DIR/report"
PYTHON_LOG="$WORK_DIR/python.log"
mkdir -p "$BIN_DIR" "$OUTPUT_DIR"
printf '<!doctype html>\n' > "$OUTPUT_DIR/index.html"

cat > "$BIN_DIR/python3" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF

cat > "$BIN_DIR/python" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == "--version" ]]; then
    printf 'Python 3.12.0\n'
    exit 0
fi
printf '%s\n' "$*" > "$PYTHON_LOG"
while true; do
    sleep 1
done
EOF

cat > "$BIN_DIR/ngrok" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

chmod +x "$BIN_DIR/python3" "$BIN_DIR/python" "$BIN_DIR/ngrok"

PATH="$BIN_DIR:$PATH" PYTHON_LOG="$PYTHON_LOG" \
    "$PLUGIN_DIR/scripts/start-ngrok.sh" --output-dir "$OUTPUT_DIR" --port 18080

if [[ "$(cat "$PYTHON_LOG")" != "-m http.server 18080" ]]; then
    echo "FAIL: expected start-ngrok.sh to fall back to the working python command" >&2
    exit 1
fi

echo "PASS: start-ngrok.sh skips a broken python3 command and uses python"
