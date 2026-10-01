#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GO_BIN=${QEMU_DOCKER_GO:-go}
PROXY_DIR=${QEMU_DOCKER_PROXY_DIR:-"$PLUGIN_DIR/../../build/qemu-docker-proxy"}
mkdir -p "$PROXY_DIR"
PROXY_DIR="$(cd "$PROXY_DIR" && pwd)"
cd "$SCRIPT_DIR/docker-proxy"
"$GO_BIN" test ./...
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) PROXY_NAME=docker.exe ;; *) PROXY_NAME=docker ;; esac
"$GO_BIN" build -o "$PROXY_DIR/$PROXY_NAME" .
echo "Docker proxy compiled." >&2
