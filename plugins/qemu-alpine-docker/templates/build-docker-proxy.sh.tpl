#!/bin/ash
set -eu
# Keep Go and its default dependency/build caches on the persistent guest disk.
if ! command -v go >/dev/null 2>&1; then
    apk add --no-cache go >&2
fi
CGO_ENABLED=0 go test ./... >&2
CGO_ENABLED=0 GOOS="$1" GOARCH="$2" go build -o proxy-bin . >&2
