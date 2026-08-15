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
    echo "${HOME}/.cache/test-reports/${project_hash}"
}

# Default configuration
OUTPUT_DIR="${REPORT_OUTPUT_DIR:-$(get_cache_dir)}"
BASE_REF="${GIT_BASE_REF:-main}"
COMPARE_REF="${GIT_COMPARE_REF:-HEAD}"
INCLUDE_UNCOMMITTED="${GIT_INCLUDE_UNCOMMITTED:-true}"

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
            echo "Generates an HTML diff report from git diff."
            echo ""
            echo "Options:"
            echo "  --output-dir DIR   Output directory for the diff report (default: ./test-reports)"
            echo "  --base-ref REF     Base git ref for comparison (default: main)"
            echo "  --compare-ref REF  Compare git ref (default: HEAD)"
            echo "  --help, -h         Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

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

# Generate stats JSON
cat > "$STATS_FILE" <<EOF
{
  "generation_time": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "base_ref": "$BASE_REF",
  "compare_ref": "$COMPARE_REF",
  "files_changed": $FILES_CHANGED,
  "insertions": $INSERTIONS,
  "deletions": $DELETIONS
}
EOF

echo "Statistics:"
echo "  Files changed: $FILES_CHANGED"
echo "  Insertions: +$INSERTIONS"
echo "  Deletions: -$DELETIONS"

# Generate HTML diff report
HTML_FILE="$OUTPUT_DIR/diff/index.html"

cat > "$HTML_FILE" <<EOF
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Code Diff Report</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        .header {
            background: #2c3e50;
            color: white;
            padding: 20px;
        }
        .header h1 {
            font-size: 1.5rem;
            margin-bottom: 10px;
        }
        .stats {
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
        }
        .stat {
            background: rgba(255,255,255,0.1);
            padding: 10px 15px;
            border-radius: 4px;
        }
        .stat-value {
            font-size: 1.2rem;
            font-weight: bold;
        }
        .stat-label {
            font-size: 0.85rem;
            opacity: 0.8;
        }
        .content {
            padding: 20px;
        }
        .diff-container {
            background: #1e1e1e;
            color: #d4d4d4;
            border-radius: 4px;
            overflow-x: auto;
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 13px;
            line-height: 1.5;
        }
        .diff-header {
            background: #2d2d2d;
            padding: 10px 15px;
            border-bottom: 1px solid #404040;
            font-weight: bold;
        }
        .diff-line {
            padding: 2px 15px;
            white-space: pre;
        }
        .diff-add {
            background: #1e3a1e;
            color: #a8ff60;
        }
        .diff-remove {
            background: #3a1e1e;
            color: #ff6060;
        }
        .diff-context {
            color: #999;
        }
        .diff-info {
            background: #1e1e3a;
            color: #9696ff;
        }
        .no-diff {
            text-align: center;
            padding: 40px;
            color: #666;
        }
        .back-link {
            display: inline-block;
            margin-top: 20px;
            color: #3498db;
            text-decoration: none;
        }
        .back-link:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Code Diff Report</h1>
            <div class="stats">
                <div class="stat">
                    <div class="stat-value">$FILES_CHANGED</div>
                    <div class="stat-label">Files Changed</div>
                </div>
                <div class="stat">
                    <div class="stat-value">+$INSERTIONS</div>
                    <div class="stat-label">Insertions</div>
                </div>
                <div class="stat">
                    <div class="stat-value">-$DELETIONS</div>
                    <div class="stat-label">Deletions</div>
                </div>
            </div>
        </div>
        <div class="content">
            <div class="diff-container" id="diff-content">
                <div class="no-diff">Loading diff...</div>
            </div>
            <a href="../index.html" class="back-link">← Back to Report</a>
        </div>
    </div>
    <script>
        // Stats are already embedded in the HTML
    </script>
</body>
</html>
EOF

# Generate diff content HTML
DIFF_HTML="$OUTPUT_DIR/diff/diff-content.html"
if [[ "$INCLUDE_UNCOMMITTED" == "true" ]]; then
    git diff "$BASE_REF" 2>/dev/null | while IFS= read -r line; do
        if [[ "$line" == @@* ]]; then
            echo "<div class=\"diff-line diff-info\">$(echo "$line" | sed 's/</\&lt;/g; s/>/\&gt;/g')</div>"
        elif [[ "$line" == +* ]]; then
            echo "<div class=\"diff-line diff-add\">$(echo "$line" | sed 's/</\&lt;/g; s/>/\&gt;/g')</div>"
        elif [[ "$line" == -* ]]; then
            echo "<div class=\"diff-line diff-remove\">$(echo "$line" | sed 's/</\&lt;/g; s/>/\&gt;/g')</div>"
        else
            echo "<div class=\"diff-line diff-context\">$(echo "$line" | sed 's/</\&lt;/g; s/>/\&gt;/g')</div>"
        fi
    done > "$DIFF_HTML" 2>/dev/null || echo "<div class=\"no-diff\">No diff available</div>" > "$DIFF_HTML"
else
    git diff "$BASE_REF"..."$COMPARE_REF" 2>/dev/null | while IFS= read -r line; do
        if [[ "$line" == @@* ]]; then
            echo "<div class=\"diff-line diff-info\">$(echo "$line" | sed 's/</\&lt;/g; s/>/\&gt;/g')</div>"
        elif [[ "$line" == +* ]]; then
            echo "<div class=\"diff-line diff-add\">$(echo "$line" | sed 's/</\&lt;/g; s/>/\&gt;/g')</div>"
        elif [[ "$line" == -* ]]; then
            echo "<div class=\"diff-line diff-remove\">$(echo "$line" | sed 's/</\&lt;/g; s/>/\&gt;/g')</div>"
        else
            echo "<div class=\"diff-line diff-context\">$(echo "$line" | sed 's/</\&lt;/g; s/>/\&gt;/g')</div>"
        fi
    done > "$DIFF_HTML" 2>/dev/null || echo "<div class=\"no-diff\">No diff available</div>" > "$DIFF_HTML"
fi

# Update HTML to include diff content
# Use a temporary file to avoid sed issues with special characters
TEMP_HTML=$(mktemp)
awk '
/<div class="no-diff">Loading diff...<\/div>/ {
    while ((getline line < "'"$DIFF_HTML"'") > 0) {
        print line
    }
    close("'"$DIFF_HTML"'")
    next
}
{ print }
' "$HTML_FILE" > "$TEMP_HTML"
mv "$TEMP_HTML" "$HTML_FILE"

echo ""
echo "Diff report generated: $HTML_FILE"
echo "Statistics written to: $STATS_FILE"