#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=/dev/null
source "${SCRIPT_DIR}/profile-utils.sh"

SDKMANAGER="$(resolve_android_tool sdkmanager)"

license_status=0

echo "Accepting Android SDK licenses." >&2
set +o pipefail
yes | "$SDKMANAGER" --licenses > /dev/null
license_status="${PIPESTATUS[1]}"
set -o pipefail

if [ "$license_status" -ne 0 ]; then
    echo "Error: Failed to accept Android SDK licenses." >&2
    exit "$license_status"
fi

echo "Android SDK license acceptance complete." >&2
