#!/bin/bash
# Compatibility entry point; new configurations use run-test-env.sh.
set -euo pipefail
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run-test-env.sh" "$@"
