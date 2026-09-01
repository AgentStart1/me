#!/usr/bin/env bash
set -euo pipefail

# generate-diff-report.sh
# Generates an HTML diff report from git diff
#
# Usage: generate-diff-report.sh [--output-dir DIR] [--base-ref REF] [--compare-ref REF]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(dirname "$SCRIPT_DIR")"

# Generate cache directory based on project path hash
get_cache_dir() {
    local project_dir="${1:-$PWD}"
    local project_hash
    project_hash=$(echo -n "$project_dir" | md5sum | cut -d' ' -f1)
    echo "${HOME}/.cache/diff-reports/${project_hash}"
}

# Default configuration
OUTPUT_DIR="${REPORT_OUTPUT_DIR:-$(get_cache_dir)}"
BASE_REF="${GIT_BASE_REF:-main}"
COMPARE_REF="${GIT_COMPARE_REF:-HEAD}"
INCLUDE_UNCOMMITTED="${GIT_INCLUDE_UNCOMMITTED:-true}"
DIFFTASTIC_COMMAND="${DIFFTASTIC_COMMAND:-difft}"
DIFFTASTIC_WIDTH="${DIFFTASTIC_WIDTH:-160}"
DIFFTASTIC_SKIP_UNCHANGED="${DIFFTASTIC_SKIP_UNCHANGED:-true}"
DIFFTASTIC_PARSE_ERROR_LIMIT="${DIFFTASTIC_PARSE_ERROR_LIMIT:-100}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --base-ref)
            BASE_REF="$2"
            shift 2
            ;;
        --compare-ref)
            COMPARE_REF="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [--output-dir DIR] [--base-ref REF] [--compare-ref REF]"
            echo ""
            echo "Generates an HTML report with selectable Git and Difftastic diff views."
            echo ""
            echo "Options:"
            echo "  --output-dir DIR   Output directory for the diff report (default: ./test-reports)"
            echo "  --base-ref REF     Base git ref for comparison (default: main)"
            echo "  --compare-ref REF  Compare git ref (default: HEAD)"
            echo ""
            echo "Environment:"
            echo "  DIFFTASTIC_COMMAND  Difftastic executable name or path (default: difft)"
            echo "  DIFFTASTIC_WIDTH    Difftastic output width (default: 160)"
            echo "  DIFFTASTIC_SKIP_UNCHANGED  Skip files with no detected changes (default: true)"
            echo "  DIFFTASTIC_PARSE_ERROR_LIMIT  Parse errors allowed before text fallback (default: 100)"
            echo "  --help, -h         Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

if [[ ! "$DIFFTASTIC_WIDTH" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: DIFFTASTIC_WIDTH must be a positive integer" >&2
    exit 1
fi

if [[ "$DIFFTASTIC_SKIP_UNCHANGED" != "true" && "$DIFFTASTIC_SKIP_UNCHANGED" != "false" ]]; then
    echo "Error: DIFFTASTIC_SKIP_UNCHANGED must be true or false" >&2
    exit 1
fi

if [[ ! "$DIFFTASTIC_PARSE_ERROR_LIMIT" =~ ^[0-9]+$ ]]; then
    echo "Error: DIFFTASTIC_PARSE_ERROR_LIMIT must be a non-negative integer" >&2
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR/diff"

echo "Generating diff report..."
echo "Base ref: $BASE_REF"
echo "Compare ref: $COMPARE_REF"

# Check if we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "Error: Not a git repository" >&2
    exit 1
fi

# Check if refs exist
if ! git rev-parse --verify "$BASE_REF" > /dev/null 2>&1; then
    echo "Warning: Base ref '$BASE_REF' not found, using HEAD~1 as fallback"
    BASE_REF="HEAD~1"
fi

# Generate diff stats
echo "Generating diff statistics..."
STATS_FILE="$OUTPUT_DIR/diff/stats.json"

# Get diff stats
if [[ "$INCLUDE_UNCOMMITTED" == "true" ]]; then
    # Include both committed and uncommitted changes
    DIFF_STATS=$(git diff --stat "$BASE_REF" 2>/dev/null || echo "No diff available")
    FILES_CHANGED=$(git diff --name-only "$BASE_REF" 2>/dev/null | wc -l || echo "0")
    INSERTIONS=$(git diff --numstat "$BASE_REF" 2>/dev/null | awk '{sum+=$1} END {print sum+0}' || echo "0")
    DELETIONS=$(git diff --numstat "$BASE_REF" 2>/dev/null | awk '{sum+=$2} END {print sum+0}' || echo "0")
else
    # Only compare between refs
    DIFF_STATS=$(git diff --stat "$BASE_REF"..."$COMPARE_REF" 2>/dev/null || echo "No diff available")
    FILES_CHANGED=$(git diff --name-only "$BASE_REF"..."$COMPARE_REF" 2>/dev/null | wc -l || echo "0")
    INSERTIONS=$(git diff --numstat "$BASE_REF"..."$COMPARE_REF" 2>/dev/null | awk '{sum+=$1} END {print sum+0}' || echo "0")
    DELETIONS=$(git diff --numstat "$BASE_REF"..."$COMPARE_REF" 2>/dev/null | awk '{sum+=$2} END {print sum+0}' || echo "0")
fi

# Detect Difftastic without making it a hard dependency.
DIFFTASTIC_AVAILABLE=false
DIFFTASTIC_BIN=""
DIFFTASTIC_WRAPPER=""
if DIFFTASTIC_BIN=$(command -v "$DIFFTASTIC_COMMAND" 2>/dev/null); then
    DIFFTASTIC_AVAILABLE=true
    DIFFTASTIC_WRAPPER=$(mktemp)
    {
        printf '#!/usr/bin/env bash\nset -euo pipefail\nDIFFTASTIC_BIN=%q\n' "$DIFFTASTIC_BIN"
        cat <<'EOF'
if [[ "${DFT_REPORT_WITH_SOURCES:-}" == "yes" ]]; then
    diff_json=$("$DIFFTASTIC_BIN" "$@")
    lhs_source=$(base64 < "$2" | tr -d '\r\n')
    rhs_source=$(base64 < "$5" | tr -d '\r\n')
    diff_payload=$(printf '%s' "$diff_json" | base64 | tr -d '\r\n')
    printf '%s\t%s\t%s\n' "$lhs_source" "$rhs_source" "$diff_payload"
else
    exec "$DIFFTASTIC_BIN" "$@"
fi
EOF
    } > "$DIFFTASTIC_WRAPPER"
    chmod +x "$DIFFTASTIC_WRAPPER"
fi

cleanup() {
    if [[ -n "$DIFFTASTIC_WRAPPER" ]]; then
        rm -f "$DIFFTASTIC_WRAPPER"
    fi
}
trap cleanup EXIT

DIFFTASTIC_COMMAND_HTML=$(printf '%s' "$DIFFTASTIC_COMMAND" | sed 's/\&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')

# Generate stats JSON
cat > "$STATS_FILE" <<EOF
{
  "generation_time": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "base_ref": "$BASE_REF",
  "compare_ref": "$COMPARE_REF",
  "files_changed": $FILES_CHANGED,
  "insertions": $INSERTIONS,
  "deletions": $DELETIONS,
  "difftastic_available": $DIFFTASTIC_AVAILABLE,
  "difftastic_skip_unchanged": $DIFFTASTIC_SKIP_UNCHANGED,
  "difftastic_parse_error_limit": $DIFFTASTIC_PARSE_ERROR_LIMIT
}
EOF

echo "Statistics:"
echo "  Files changed: $FILES_CHANGED"
echo "  Insertions: +$INSERTIONS"
echo "  Deletions: -$DELETIONS"

# Generate HTML diff report
HTML_FILE="$OUTPUT_DIR/diff/index.html"

DIFFTASTIC_DISABLED=""
GIT_SELECTED=" selected"
DIFFTASTIC_SELECTED=""
GIT_VIEW_HIDDEN=""
DIFFTASTIC_VIEW_HIDDEN=" hidden"
if [[ "$DIFFTASTIC_AVAILABLE" != "true" ]]; then
    DIFFTASTIC_DISABLED=" disabled"
    DIFFTASTIC_NOTE="Difftastic is unavailable because $DIFFTASTIC_COMMAND_HTML was not found."
else
    DIFFTASTIC_NOTE="Choose the renderer used for this comparison."
    GIT_SELECTED=""
    DIFFTASTIC_SELECTED=" selected"
    GIT_VIEW_HIDDEN=" hidden"
    DIFFTASTIC_VIEW_HIDDEN=""
fi

render_diff_template() {
    local template="$PLUGIN_DIR/templates/diff-report.html"
    local stylesheet="$PLUGIN_DIR/templates/diff-report.css"
    if [[ ! -f "$template" ]] || [[ ! -f "$stylesheet" ]]; then
        echo "Error: Diff report template or stylesheet is missing" >&2
        exit 1
    fi
    cp "$stylesheet" "$OUTPUT_DIR/diff/diff-report.css"
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line//@@FILES_CHANGED@@/$FILES_CHANGED}"
        line="${line//@@INSERTIONS@@/$INSERTIONS}"
        line="${line//@@DELETIONS@@/$DELETIONS}"
        line="${line//@@DIFFTASTIC_DISABLED@@/$DIFFTASTIC_DISABLED}"
        line="${line//@@GIT_SELECTED@@/$GIT_SELECTED}"
        line="${line//@@DIFFTASTIC_SELECTED@@/$DIFFTASTIC_SELECTED}"
        line="${line//@@GIT_VIEW_HIDDEN@@/$GIT_VIEW_HIDDEN}"
        line="${line//@@DIFFTASTIC_VIEW_HIDDEN@@/$DIFFTASTIC_VIEW_HIDDEN}"
        line="${line//@@DIFFTASTIC_NOTE@@/$DIFFTASTIC_NOTE}"
        printf '%s\n' "$line"
    done < "$template"
}

render_diff_template > "$HTML_FILE"

# Generate Git diff content HTML.
GIT_DIFF_HTML="$OUTPUT_DIR/diff/git-diff-content.html"
generate_git_diff() {
    if [[ "$INCLUDE_UNCOMMITTED" == "true" ]]; then
        git diff "$BASE_REF"
    else
        git diff "$BASE_REF"..."$COMPARE_REF"
    fi
}

generate_git_diff 2>/dev/null | while IFS= read -r line; do
        if [[ "$line" == @@* ]]; then
            echo "<div class=\"diff-line diff-info\">$(printf '%s' "$line" | sed 's/\&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')</div>"
        elif [[ "$line" == +* ]]; then
            echo "<div class=\"diff-line diff-add\">$(printf '%s' "$line" | sed 's/\&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')</div>"
        elif [[ "$line" == -* ]]; then
            echo "<div class=\"diff-line diff-remove\">$(printf '%s' "$line" | sed 's/\&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')</div>"
        else
            echo "<div class=\"diff-line diff-context\">$(printf '%s' "$line" | sed 's/\&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')</div>"
        fi
    done > "$GIT_DIFF_HTML" 2>/dev/null || echo "<div class=\"no-diff\">No Git diff available</div>" > "$GIT_DIFF_HTML"

# Generate Difftastic content when the executable is available. Git invokes the
# external diff once per changed file; DFT_* keeps the captured output static.
DIFFTASTIC_HTML="$OUTPUT_DIR/diff/difftastic-diff-content.html"
generate_difftastic_diff() {
    if [[ "$INCLUDE_UNCOMMITTED" == "true" ]]; then
        GIT_EXTERNAL_DIFF="$DIFFTASTIC_WRAPPER" DFT_REPORT_WITH_SOURCES=yes DFT_UNSTABLE=yes DFT_DISPLAY=json DFT_WIDTH="$DIFFTASTIC_WIDTH" DFT_SKIP_UNCHANGED="$DIFFTASTIC_SKIP_UNCHANGED" DFT_PARSE_ERROR_LIMIT="$DIFFTASTIC_PARSE_ERROR_LIMIT" git diff "$BASE_REF"
    else
        GIT_EXTERNAL_DIFF="$DIFFTASTIC_WRAPPER" DFT_REPORT_WITH_SOURCES=yes DFT_UNSTABLE=yes DFT_DISPLAY=json DFT_WIDTH="$DIFFTASTIC_WIDTH" DFT_SKIP_UNCHANGED="$DIFFTASTIC_SKIP_UNCHANGED" DFT_PARSE_ERROR_LIMIT="$DIFFTASTIC_PARSE_ERROR_LIMIT" git diff "$BASE_REF"..."$COMPARE_REF"
    fi
}

if [[ "$DIFFTASTIC_AVAILABLE" == "true" ]]; then
    DIFFTASTIC_JSON="$OUTPUT_DIR/diff/difftastic.jsonl"
    if generate_difftastic_diff 2>/dev/null > "$DIFFTASTIC_JSON"; then
        if [[ -s "$DIFFTASTIC_JSON" ]]; then
            DIFFTASTIC_BASE64=$(base64 < "$DIFFTASTIC_JSON" | tr -d '\r\n')
            cat > "$DIFFTASTIC_HTML" <<EOF
<div class="difftastic-layout" id="difftastic-inline-view">
    <div class="difftastic-output" id="difftastic-inline-output">Rendering Difftastic JSON...</div>
</div>
<div class="difftastic-layout" id="difftastic-side-by-side-view" hidden>
    <div class="difftastic-output" id="difftastic-side-by-side-output">Rendering Difftastic JSON...</div>
</div>
<script type="application/json" id="difftastic-json">$DIFFTASTIC_BASE64</script>
EOF
        else
            echo "<div class=\"no-diff\">No Difftastic diff available</div>" > "$DIFFTASTIC_HTML"
        fi
    else
        echo "<div class=\"no-diff\">Difftastic failed to generate JSON output</div>" > "$DIFFTASTIC_HTML"
    fi
else
    echo "<div class=\"no-diff\">Difftastic executable '$DIFFTASTIC_COMMAND_HTML' was not found</div>" > "$DIFFTASTIC_HTML"
fi

# Update HTML to include both diff fragments.
TEMP_HTML=$(mktemp)
awk '
/<div class="no-diff">Loading Git diff...<\/div>/ {
    while ((getline line < "'"$GIT_DIFF_HTML"'") > 0) {
        print line
    }
    close("'"$GIT_DIFF_HTML"'")
    next
}
{ print }
' "$HTML_FILE" > "$TEMP_HTML"
mv "$TEMP_HTML" "$HTML_FILE"

TEMP_HTML=$(mktemp)
awk '
/<div class="no-diff">Loading Difftastic diff...<\/div>/ {
    while ((getline line < "'"$DIFFTASTIC_HTML"'") > 0) {
        print line
    }
    close("'"$DIFFTASTIC_HTML"'")
    next
}
{ print }
' "$HTML_FILE" > "$TEMP_HTML"
mv "$TEMP_HTML" "$HTML_FILE"

echo ""
echo "Diff report generated: $HTML_FILE"
echo "Statistics written to: $STATS_FILE"
