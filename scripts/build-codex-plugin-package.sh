#!/usr/bin/env bash
set -euo pipefail

# Builds Codex-compatible plugin packages without modifying Claude-oriented
# source skills. By default, generated artifacts are written to ../me.codex.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_DIR="$(dirname "$SCRIPT_DIR")"
DEFAULT_OUTPUT_DIR="$REPOSITORY_DIR/../me.codex"
MARKETPLACE_TEMPLATE="$SCRIPT_DIR/templates/marketplace.json.template"
README_TEMPLATE="$SCRIPT_DIR/templates/codex-readme.md.template"

usage() {
    cat <<'EOF'
Usage:
  build-codex-plugin-package.sh --all [--output-dir directory]

Build Codex-compatible plugin packages. Generated packages have their own
.codex-plugin/plugin.json and ./skills/ directory. Claude routing fields
(context and agent) are removed only from generated SKILL.md copies. Output is
written directly to the standalone sibling repository ../me.codex by default.

Options:
  --all               Build every plugin under plugins/ and generate the
                      Codex marketplace in ../me.codex.
  --output-dir DIR    Override the output directory (primarily for tests).
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
    local output_dir="$1"
    local source_root output_root plugin_dir plugin_name

    if [[ ! -f "$MARKETPLACE_TEMPLATE" ]]; then
        echo "Error: marketplace template is missing: $MARKETPLACE_TEMPLATE" >&2
        return 1
    fi
    if [[ ! -f "$README_TEMPLATE" ]]; then
        echo "Error: Codex README template is missing: $README_TEMPLATE" >&2
        return 1
    fi

    mkdir -p "$output_dir"
    source_root="$(cd "$REPOSITORY_DIR" && pwd -P)"
    output_root="$(cd "$output_dir" && pwd -P)"

    if [[ "$output_root" == "$source_root" ]]; then
        echo "Error: refusing to generate over the source repository" >&2
        return 1
    fi
    if [[ "$(basename "$output_root")" != "me.codex" ]]; then
        echo "Error: output directory must be named me.codex: $output_root" >&2
        return 1
    fi

    rm -rf "$output_root/plugins" "$output_root/.agents/plugins"
    mkdir -p "$output_root/plugins" "$output_root/.agents/plugins"

    for plugin_dir in "$REPOSITORY_DIR"/plugins/*; do
        [[ -d "$plugin_dir/.codex-plugin" ]] || continue
        plugin_name="$(basename "$plugin_dir")"
        build_plugin "$plugin_dir" "$output_root/plugins/$plugin_name"
    done

    cp "$MARKETPLACE_TEMPLATE" "$output_root/.agents/plugins/marketplace.json"
    cp "$README_TEMPLATE" "$output_root/README.md"
    echo "Codex marketplace built: $output_root/.agents/plugins/marketplace.json"
    echo "Codex output root: $output_root"
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
    OUTPUT_DIR="$DEFAULT_OUTPUT_DIR"
    if [[ $# -eq 3 && "$2" == "--output-dir" ]]; then
        OUTPUT_DIR="$3"
    elif [[ $# -ne 1 ]]; then
        echo "Error: expected --all with an optional --output-dir directory" >&2
        exit 1
    fi
    build_all "$OUTPUT_DIR"
    exit 0
fi

echo "Error: only --all is supported; Codex packages are generated together in ../me.codex." >&2
usage >&2
exit 1
