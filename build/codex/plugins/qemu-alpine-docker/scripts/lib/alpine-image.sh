# Alpine ISO download and checksum verification.
# Depends on runtime.sh and IMAGES_DIR from ../vm-utils.sh.

download_file() {
    local url="$1" dest="$2"
    mkdir -p "$(dirname "$dest")"
    if command -v curl >/dev/null 2>&1; then
        curl -fSL --retry 3 --retry-delay 5 -o "$dest" "$url"
    elif command -v wget >/dev/null 2>&1; then
        wget -q --tries=3 -O "$dest" "$url"
    else
        echo "Error: Neither curl nor wget is available." >&2
        return 1
    fi
}

ALPINE_IMAGE_URL="${ALPINE_IMAGE_URL:-https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/x86_64/alpine-virt-3.24.1-x86_64.iso}"
ALPINE_IMAGE_NAME="${ALPINE_IMAGE_NAME:-alpine-virt-3.24.1-x86_64.iso}"

ensure_alpine_image() {
    local image_path="${IMAGES_DIR}/${ALPINE_IMAGE_NAME}"
    local checksum_path="${image_path}.sha256"
    [ -f "$image_path" ] || download_file "$ALPINE_IMAGE_URL" "$image_path"
    [ -f "$checksum_path" ] || download_file "${ALPINE_IMAGE_URL}.sha256" "$checksum_path"
    require_command sha256sum
    (cd "$IMAGES_DIR" && sha256sum -c "$(basename "$checksum_path")") >&2
    echo "$image_path"
}
