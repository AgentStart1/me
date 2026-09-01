#!/usr/bin/env bash
set -euo pipefail

# Assembles the standalone static site for a generated code diff.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"

get_cache_dir() {
    local project_dir="${1:-$PWD}"
    local project_hash
    project_hash=$(echo -n "$project_dir" | md5sum | cut -d' ' -f1)
    echo "${HOME}/.cache/diff-reports/${project_hash}"
}

OUTPUT_DIR="${REPORT_OUTPUT_DIR:-$(get_cache_dir)}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [--output-dir DIR]"
            echo "Assembles the static site for a generated code diff."
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

mkdir -p "$OUTPUT_DIR"
cp "$PLUGIN_DIR/templates/style.css" "$OUTPUT_DIR/style.css"

read_diff_stat() {
    local stats_file="$1"
    local field="$2"
    if command -v jq >/dev/null 2>&1; then
        jq -r ".$field" "$stats_file"
    else
        sed -n "s/.*\"$field\"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p" "$stats_file" | head -n 1
    fi
}

generate_diff_section() {
    local diff_dir="$OUTPUT_DIR/diff"
    if [[ ! -f "$diff_dir/index.html" ]]; then
        cat <<EOF
        <div class="section">
            <h2>📝 Code Diff</h2>
            <p class="no-data">No diff report generated. Run generate-diff-report.sh first.</p>
        </div>
EOF
        return
    fi

    local stats_file="$diff_dir/stats.json"
    if [[ -f "$stats_file" ]]; then
        local files_changed insertions deletions
        files_changed=$(read_diff_stat "$stats_file" "files_changed")
        insertions=$(read_diff_stat "$stats_file" "insertions")
        deletions=$(read_diff_stat "$stats_file" "deletions")
        cat <<EOF
        <div class="section">
            <h2>📝 Code Diff</h2>
            <p>$files_changed file(s) changed. Git line stats: <span class="insertions">+$insertions</span> / <span class="deletions">-$deletions</span></p>
            <a href="diff/index.html" class="btn">View Full Diff</a>
        </div>
EOF
        return
    fi

    cat <<EOF
        <div class="section">
            <h2>📝 Code Diff</h2>
            <a href="diff/index.html" class="btn">View Diff Report</a>
        </div>
EOF
}

GENERATED_AT=$(date +"%Y-%m-%d %H:%M:%S")
DIFF_SECTION=$(generate_diff_section)
TEMPLATE="$PLUGIN_DIR/templates/diff-site.html"

while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
        *'<!-- @@DIFF_SECTION@@ -->'*)
            printf '%s\n' "$DIFF_SECTION"
            ;;
        *)
            printf '%s\n' "${line//@@GENERATED_AT@@/$GENERATED_AT}"
            ;;
    esac
done < "$TEMPLATE" > "$OUTPUT_DIR/index.html"

echo "Diff site generated: $OUTPUT_DIR/index.html"
