#!/usr/bin/env bash
# Test argument handling and dispatch; package contents are checked in Python.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_DIR="$(dirname "$SCRIPT_DIR")"
TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT

expect_failure() {
    if "$@" > "$TEST_ROOT/error.log" 2>&1; then
        echo "FAIL: expected nonzero exit: $*" >&2
        exit 1
    fi
}

# Capture default dispatch without overwriting either sibling distribution.
mkdir "$TEST_ROOT/bin"
cat > "$TEST_ROOT/bin/python3" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$CLI_TEST_ARGUMENTS"
EOF
chmod +x "$TEST_ROOT/bin/python3"

for client in claude codex; do
    entry="$REPOSITORY_DIR/scripts/build-$client-plugin-package.sh"
    for option in --help -h; do
        "$entry" "$option" > "$TEST_ROOT/help.log"
        grep -Fq -- '--all [--output-dir directory]' "$TEST_ROOT/help.log"
    done
    expect_failure "$entry"
    expect_failure "$entry" --unknown
    expect_failure "$entry" --output-dir "$TEST_ROOT/me.$client"
    expect_failure "$entry" --all --unknown
    expect_failure "$entry" --all --output-dir

    PATH="$TEST_ROOT/bin:$PATH" CLI_TEST_ARGUMENTS="$TEST_ROOT/arguments" "$entry" --all
    printf '%s\n' "$REPOSITORY_DIR/scripts/build-plugin-packages.py" --client "$client" > "$TEST_ROOT/expected"
    cmp "$TEST_ROOT/expected" "$TEST_ROOT/arguments"

    # Exercise the real entry and --output-dir; detailed integrity belongs to Python.
    "$entry" --all --output-dir "$TEST_ROOT/me.$client"
    test -f "$TEST_ROOT/me.$client/README.md"
    echo "PASS: $client CLI help, argument errors, default dispatch, and output override"
done
