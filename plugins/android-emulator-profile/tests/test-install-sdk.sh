#!/usr/bin/env bash
# Simulated archive download, SDK commands and ownership; no network or device IO.
set -euo pipefail
PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fixture="$(mktemp -d)"
trap 'rm -rf "$fixture"' EXIT
mkdir "$fixture/bin" "$fixture/project"
export FAKE_ARCHIVE="$fixture/tools.zip" FAKE_LOG="$fixture/calls"
cat > "$fixture/bin/curl" <<'MOCK'
#!/usr/bin/env bash
while [ $# -gt 0 ]; do if [ "$1" = -o ]; then cp "$FAKE_ARCHIVE" "$2"; echo download >> "$FAKE_LOG"; exit; fi; shift; done
exit 1
MOCK
cat > "$fixture/bin/sdkmanager" <<'MOCK'
#!/usr/bin/env bash
echo "sdkmanager $*" >> "$FAKE_LOG"
exit 0
MOCK
cat > "$fixture/bin/sudo" <<'MOCK'
#!/usr/bin/env bash
echo forbidden-sudo >> "$FAKE_LOG"
exit 99
MOCK
chmod +x "$fixture/bin/"*
export PATH="$fixture/bin:$PATH"
python3 - "$FAKE_ARCHIVE" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1], 'w') as archive:
    entry = zipfile.ZipInfo('cmdline-tools/bin/sdkmanager')
    entry.external_attr = 0o100755 << 16
    archive.writestr(entry, '#!/bin/sh\nexit 0\n')
    archive.writestr('cmdline-tools/source.properties', 'Pkg.Revision=20.0\n')
PY
cd "$fixture/project"
printf project-owned > commandline-tools.zip
export ANDROID_HOME="$fixture/sdk"
bash "$PLUGIN_DIR/scripts/install-sdk.sh" > "$fixture/install.log" 2>&1
[ -f "$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" ]
[ "$(cat commandline-tools.zip)" = project-owned ]
! grep -q forbidden-sudo "$FAKE_LOG"
printf 'Pkg.Revision=20.0.1\n' > "$ANDROID_HOME/cmdline-tools/latest/source.properties"
bash "$PLUGIN_DIR/scripts/install-sdk.sh" >> "$fixture/install.log" 2>&1
[ "$(grep -c '^download$' "$FAKE_LOG")" = 1 ]
printf 'Pkg.Revision=19.0\n' > "$ANDROID_HOME/cmdline-tools/latest/source.properties"
touch "$ANDROID_HOME/cmdline-tools/latest/preserved-file"
bash "$PLUGIN_DIR/scripts/install-sdk.sh" >> "$fixture/install.log" 2>&1
[ "$(find "$ANDROID_HOME/cmdline-tools" -path '*/previous.*/latest/preserved-file' | wc -l | tr -d ' ')" = 1 ]
[ "$(cat commandline-tools.zip)" = project-owned ]
echo 'PASS: SDK download stays outside project, existing ownership is respected, newer tools reused and previous tools preserved'
