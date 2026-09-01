#!/usr/bin/env bash
set -euo pipefail

# Builds Codex-compatible plugin packages without modifying Claude-oriented
# source skills. All generated Codex artifacts live under the repository build/codex/.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$REPOSITORY_DIR/build/codex"
MARKETPLACE_TEMPLATE="$SCRIPT_DIR/templates/marketplace.json.template"

usage() {
    cat <<'EOF'
Usage:
  build-codex-plugin-package.sh --all

Build Codex-compatible plugin packages. Generated packages have their own
.codex-plugin/plugin.json and ./skills/ directory. Claude routing fields
(context and agent) are removed only from generated SKILL.md copies.

Options:
  --all               Build every plugin under plugins/ and generate the
                      Codex marketplace at build/codex/.agents/plugins/marketplace.json.
  --help, -h          Show this help message.
EOF
}

build_plugin() {
    local plugin_dir="$1"
    local output_dir="$2"
    local source_skill skill_name output_skill source_entry entry_name

    if [[ ! -f "$plugin_dir/.codex-plugin/plugin.json" || ! -d "$plugin_dir/skills" ]]; then
        echo "Error: $plugin_dir is not a plugin source with .codex-plugin/plugin.json and skills/" >&2
        return 1
    fi

    rm -rf "$output_dir"
    mkdir -p "$output_dir/.codex-plugin" "$output_dir/skills"
    cp "$plugin_dir/.codex-plugin/plugin.json" "$output_dir/.codex-plugin/plugin.json"

    shopt -s nullglob
    for source_entry in "$plugin_dir"/* "$plugin_dir"/.[!.]* "$plugin_dir"/..?*; do
        entry_name="$(basename "$source_entry")"
        case "$entry_name" in
            .codex-plugin|.claude-plugin|agents|skills|build)
                continue
                ;;
        esac
        cp -R "$source_entry" "$output_dir/"
    done
    shopt -u nullglob

    for source_skill in "$plugin_dir"/skills/*; do
        [[ -d "$source_skill" ]] || continue
        skill_name="$(basename "$source_skill")"
        output_skill="$output_dir/skills/$skill_name"
        mkdir -p "$output_skill"

        awk '
            NR == 1 && $0 == "---" { in_frontmatter = 1 }
            in_frontmatter && $0 ~ /^(context|agent):[[:space:]]*/ { next }
            { print }
            in_frontmatter && NR > 1 && $0 == "---" { in_frontmatter = 0 }
        ' "$source_skill/SKILL.md" > "$output_skill/SKILL.md"
    done

    if grep -R -Eq '^(context|agent):[[:space:]]*' "$output_dir/skills"; then
        echo "Error: generated skills still contain Claude routing fields: $output_dir" >&2
        return 1
    fi

    echo "Codex package built: $output_dir"
}

build_all() {
    local plugin_dir plugin_name

    if [[ ! -f "$MARKETPLACE_TEMPLATE" ]]; then
        echo "Error: marketplace template is missing: $MARKETPLACE_TEMPLATE" >&2
        return 1
    fi

    rm -rf "$BUILD_DIR"
    mkdir -p "$BUILD_DIR/plugins" "$BUILD_DIR/.agents/plugins"

    for plugin_dir in "$REPOSITORY_DIR"/plugins/*; do
        [[ -d "$plugin_dir/.codex-plugin" ]] || continue
        plugin_name="$(basename "$plugin_dir")"
        build_plugin "$plugin_dir" "$BUILD_DIR/plugins/$plugin_name"
    done

    cp "$MARKETPLACE_TEMPLATE" "$BUILD_DIR/.agents/plugins/marketplace.json"
    echo "Codex marketplace built: $BUILD_DIR/.agents/plugins/marketplace.json"
    echo "Build root: $BUILD_DIR"
}

if [[ $# -eq 0 ]]; then
    usage >&2
    exit 1
fi

if [[ "$1" == "--help" || "$1" == "-h" ]]; then
    usage
    exit 0
fi

if [[ "$1" == "--all" ]]; then
    [[ $# -eq 1 ]] || { echo "Error: --all does not accept additional arguments" >&2; exit 1; }
    build_all
    exit 0
fi

echo "Error: only --all is supported; Codex packages are generated together under build/codex/." >&2
usage >&2
exit 1
