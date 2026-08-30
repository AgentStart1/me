#!/bin/ash
# Select and persist a usable Alpine package mirror during guest provisioning.
#
# This script runs INSIDE the guest during the installation phase.
# It uses /bin/ash (not bash) because Alpine's minimal install doesn't include bash.
#
# Mirror selection strategy:
#   1. If ALPINE_MIRROR_BASE is "auto":
#      a. Use Alpine's built-in fastest-mirror detection (setup-apkrepos -cf)
#      b. Verify the detected mirror supports HTTPS (for security)
#      c. If HTTPS fails, fall back to the official CDN
#      d. If detection fails entirely, fall back to the official CDN
#   2. If ALPINE_MIRROR_BASE is a URL:
#      a. Validate the mirror URL (must be http:// or https://, safe characters)
#      b. Write the mirror to /etc/apk/repositories
#      c. Verify the mirror is reachable via apk update
#      d. If unreachable, fail with an error
#
# The selected mirror is persisted to /etc/qemu-alpine-docker-mirror and
# the answers file (APKREPOSOPTS) is updated with the selected mirror.
# This ensures subsequent runs of the guest setup script use the same mirror.
#
# Arguments:
#   $1 — Alpine branch (default: v3.24)
#   $2 — Mirror base URL or "auto" (default: auto)
#   $3 — Answers file path (default: /answers)
#
set -eu

ALPINE_BRANCH="${1:-v3.24}"
ALPINE_MIRROR_BASE="${2:-auto}"
ANSWERS_FILE="${3:-/answers}"
REPOSITORIES_FILE="${APK_REPOSITORIES_FILE:-/etc/apk/repositories}"
SELECTED_MIRROR_FILE="${ALPINE_SELECTED_MIRROR_FILE:-/etc/qemu-alpine-docker-mirror}"
FALLBACK_MIRROR="${ALPINE_FALLBACK_MIRROR:-https://dl-cdn.alpinelinux.org/alpine}"

# Strip trailing slashes from a mirror URL for consistent formatting.
normalize_mirror_base() {
    local base="$1"
    while [ "${base%/}" != "$base" ]; do base="${base%/}"; done
    printf '%s\n' "$base"
}

# Validate that a mirror URL uses http:// or https:// and contains only safe characters.
# Rejects URLs with shell metacharacters or unexpected protocols (file://, ftp://, etc.).
validate_mirror_base() {
    local base="$1"
    case "$base" in
        http://*|https://*) ;;
        *) echo "Error: Alpine mirror must use http:// or https://: ${base}" >&2; return 1 ;;
    esac
    case "$base" in
        *[!A-Za-z0-9.:/_~-]*)
            echo "Error: Alpine mirror contains unsupported characters: ${base}" >&2
            return 1
            ;;
    esac
}

# Write the main and community repositories to /etc/apk/repositories.
# This file tells apk where to find packages.
write_repositories() {
    local base="$1"
    mkdir -p "$(dirname "$REPOSITORIES_FILE")"
    printf '%s/%s/main\n%s/%s/community\n' \
        "$base" "$ALPINE_BRANCH" "$base" "$ALPINE_BRANCH" > "$REPOSITORIES_FILE"
}

# Check if the current repositories are usable by running apk update.
repositories_are_usable() { apk update >/dev/null 2>&1; }

# Extract the base URL from the current /etc/apk/repositories file.
# Looks for the first line matching http(s)://.../branch/main and strips the branch suffix.
selected_base_from_repositories() {
    local repository suffix="/${ALPINE_BRANCH}/main"
    while IFS= read -r repository || [ -n "$repository" ]; do
        case "$repository" in
            http://*"$suffix"|https://*"$suffix")
                printf '%s\n' "${repository%$suffix}"
                return 0
                ;;
        esac
    done < "$REPOSITORIES_FILE"
    return 1
}

# Update the answers file with the selected mirror repository URLs.
# This ensures that if setup-alpine.sh is re-run, it uses the selected mirror.
# Uses awk to replace or append the APKREPOSOPTS line.
persist_answer_repositories() {
    local base="$1" replacement temp_file
    [ -f "$ANSWERS_FILE" ] || return 0
    replacement="APKREPOSOPTS=\"${base}/${ALPINE_BRANCH}/main ${base}/${ALPINE_BRANCH}/community\""
    temp_file="${ANSWERS_FILE}.tmp"
    awk -v replacement="$replacement" '
        /^APKREPOSOPTS=/ { print replacement; replaced=1; next }
        { print }
        END { if (!replaced) print replacement }
    ' "$ANSWERS_FILE" > "$temp_file"
    mv "$temp_file" "$ANSWERS_FILE"
}

# Automatic mirror selection: try Alpine's fastest-mirror detection, verify HTTPS,
# and fall back to the official CDN if anything fails.
# Returns the selected mirror base URL.
select_automatic_mirror() {
    local selected secure_selected
    if setup-apkrepos -cf >/dev/null 2>&1; then
        selected="$(selected_base_from_repositories 2>/dev/null || true)"
        if [ -n "$selected" ]; then
            secure_selected="$selected"
            case "$secure_selected" in
                http://*) secure_selected="https://${secure_selected#http://}" ;;
            esac
            secure_selected="$(normalize_mirror_base "$secure_selected")"
            if validate_mirror_base "$secure_selected" && \
               write_repositories "$secure_selected" && repositories_are_usable; then
                printf '%s\n' "$secure_selected"
                return 0
            fi
            echo "Fastest mirror failed HTTPS validation; using the official CDN." >&2
        else
            echo "Fastest-mirror detection returned no usable repository; using the official CDN." >&2
        fi
    else
        echo "Fastest-mirror detection failed; using the official CDN." >&2
    fi

    FALLBACK_MIRROR="$(normalize_mirror_base "$FALLBACK_MIRROR")"
    validate_mirror_base "$FALLBACK_MIRROR"
    write_repositories "$FALLBACK_MIRROR"
    repositories_are_usable || {
        echo "Error: official Alpine CDN is unavailable: ${FALLBACK_MIRROR}" >&2
        return 1
    }
    printf '%s\n' "$FALLBACK_MIRROR"
}

# --- Main logic ---
# Validate the Alpine branch format (e.g., v3.24, edge)
case "$ALPINE_BRANCH" in
    edge|v[0-9]*.[0-9]*) ;;
    *) echo "Error: unsupported Alpine branch: ${ALPINE_BRANCH}" >&2; exit 1 ;;
esac

# Select the mirror: automatic detection or manual override
if [ "$ALPINE_MIRROR_BASE" = "auto" ]; then
    SELECTED_MIRROR="$(select_automatic_mirror)"
else
    # Manual mirror: validate, write repositories, verify reachability
    SELECTED_MIRROR="$(normalize_mirror_base "$ALPINE_MIRROR_BASE")"
    validate_mirror_base "$SELECTED_MIRROR"
    write_repositories "$SELECTED_MIRROR"
    repositories_are_usable || {
        echo "Error: configured Alpine mirror is unavailable: ${SELECTED_MIRROR}" >&2
        exit 1
    }
fi

# Persist the selected mirror to the answers file and the mirror file
persist_answer_repositories "$SELECTED_MIRROR"
mkdir -p "$(dirname "$SELECTED_MIRROR_FILE")"
printf '%s\n' "$SELECTED_MIRROR" > "$SELECTED_MIRROR_FILE"
# Output the selected mirror to stdout (for the calling script to capture)
printf '%s\n' "$SELECTED_MIRROR"
