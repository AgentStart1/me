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
DIFFTASTIC_COMMAND="${DIFFTASTIC_COMMAND:-difft}"
DIFFTASTIC_WIDTH="${DIFFTASTIC_WIDTH:-160}"

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
  "difftastic_available": $DIFFTASTIC_AVAILABLE
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
        .stats[hidden] {
            display: none;
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
        .view-controls {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 15px;
        }
        .view-controls select {
            padding: 8px 12px;
            border: 1px solid #bbb;
            border-radius: 4px;
            background: white;
        }
        .view-note {
            color: #666;
            font-size: 0.9rem;
        }
        .diff-view[hidden] {
            display: none;
        }
        .difftastic-layout[hidden],
        #difftastic-layout-control[hidden] {
            display: none;
        }
        .difftastic-output {
            padding: 12px 15px;
            white-space: pre;
        }
        .structural-file {
            border-bottom: 1px solid #404040;
        }
        .structural-file:last-child {
            border-bottom: 0;
        }
        .structural-file-header {
            padding: 10px 15px;
            background: #2d2d2d;
            color: #f4e66a;
            font-weight: 700;
        }
        .structural-row {
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
            border-top: 1px solid #303030;
        }
        .structural-cell {
            display: flex;
            min-width: 0;
            padding: 5px 10px;
        }
        .structural-cell + .structural-cell {
            border-left: 1px solid #404040;
        }
        .structural-line-number {
            flex: 0 0 3.25em;
            color: #777;
            text-align: right;
            padding-right: 12px;
            user-select: none;
        }
        .structural-code {
            white-space: pre-wrap;
            overflow-wrap: anywhere;
        }
        .structural-change-remove {
            color: #ff5f5f;
            font-weight: 700;
        }
        .structural-change-add {
            color: #8fe234;
            font-weight: 700;
        }
        .structural-gap {
            color: #777;
            padding: 0 0.35em;
        }
        .structural-inline-row {
            border-top: 1px solid #303030;
        }
        .structural-inline-row .structural-cell {
            width: 100%;
        }
        .structural-separator {
            padding: 2px 15px 2px 5.5em;
            color: #777;
            border-top: 1px solid #303030;
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
            <div class="stats" id="git-stats">
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
            <div class="stats" id="difftastic-stats" hidden>
                <div class="stat">
                    <div class="stat-value">$FILES_CHANGED</div>
                    <div class="stat-label">Files Compared</div>
                </div>
                <div class="stat">
                    <div class="stat-value">Structural</div>
                    <div class="stat-label">Diff Model</div>
                </div>
                <div class="stat">
                    <div class="stat-value" id="difftastic-display-value">Inline</div>
                    <div class="stat-label">Display Mode</div>
                </div>
            </div>
        </div>
        <div class="content">
            <div class="view-controls">
                <label for="diff-renderer">Diff renderer:</label>
                <select id="diff-renderer">
                    <option value="git">Git diff</option>
                    <option value="difftastic"$(if [[ "$DIFFTASTIC_AVAILABLE" != "true" ]]; then printf ' disabled'; fi)>Difftastic</option>
                </select>
                <span id="difftastic-layout-control" hidden>
                    <label for="difftastic-layout">Layout:</label>
                    <select id="difftastic-layout">
                        <option value="inline">Inline</option>
                        <option value="side-by-side">Side by side</option>
                    </select>
                </span>
                <span class="view-note">$(if [[ "$DIFFTASTIC_AVAILABLE" == "true" ]]; then printf 'Choose the renderer used for this comparison.'; else printf 'Difftastic is unavailable because %s was not found.' "$DIFFTASTIC_COMMAND_HTML"; fi)</span>
            </div>
            <div class="diff-container diff-view" id="git-view">
                <div class="no-diff">Loading Git diff...</div>
            </div>
            <div class="diff-container diff-view" id="difftastic-view" hidden>
                <div class="no-diff">Loading Difftastic diff...</div>
            </div>
            <a href="../index.html" class="back-link">← Back to Report</a>
        </div>
    </div>
    <script>
        const renderer = document.getElementById('diff-renderer');
        const gitView = document.getElementById('git-view');
        const difftasticView = document.getElementById('difftastic-view');
        const gitStats = document.getElementById('git-stats');
        const difftasticStats = document.getElementById('difftastic-stats');
        const layoutControl = document.getElementById('difftastic-layout-control');
        const layout = document.getElementById('difftastic-layout');
        const inlineView = document.getElementById('difftastic-inline-view');
        const sideBySideView = document.getElementById('difftastic-side-by-side-view');
        const displayValue = document.getElementById('difftastic-display-value');

        function updateDifftasticLayout() {
            const showSideBySide = layout.value === 'side-by-side';
            if (inlineView) inlineView.hidden = showSideBySide;
            if (sideBySideView) sideBySideView.hidden = !showSideBySide;
            displayValue.textContent = showSideBySide ? 'Side by Side' : 'Inline';
        }

        renderer.addEventListener('change', () => {
            const showDifftastic = renderer.value === 'difftastic';
            gitView.hidden = showDifftastic;
            difftasticView.hidden = !showDifftastic;
            gitStats.hidden = showDifftastic;
            difftasticStats.hidden = !showDifftastic;
            layoutControl.hidden = !showDifftastic;
        });
        layout.addEventListener('change', updateDifftasticLayout);
        updateDifftasticLayout();

        function decodePayload(payload) {
            const binary = atob(payload.textContent.trim());
            const bytes = Uint8Array.from(binary, character => character.charCodeAt(0));
            return new TextDecoder().decode(bytes);
        }

        function decodeBase64(value) {
            const binary = atob(value);
            return new TextDecoder().decode(Uint8Array.from(binary, character => character.charCodeAt(0)));
        }

        function parseDifftasticRecords(text) {
            return text.split(/\r?\n/).filter(line => line.trim()).flatMap(line => {
                const [lhsPayload, rhsPayload, diffPayload] = line.split('\t');
                const parsed = JSON.parse(decodeBase64(diffPayload));
                const values = Array.isArray(parsed) ? parsed : [parsed];
                return values.map(value => ({
                    ...value,
                    lhsLines: decodeBase64(lhsPayload).split(/\r?\n/),
                    rhsLines: decodeBase64(rhsPayload).split(/\r?\n/)
                }));
            });
        }

        function lineNumber(value) {
            const number = document.createElement('span');
            number.className = 'structural-line-number';
            number.textContent = value == null ? '·' : String(value + 1);
            return number;
        }

        function codeWithChanges(text, changes, kind) {
            const code = document.createElement('span');
            code.className = 'structural-code';
            let cursor = 0;
            (changes || []).slice().sort((a, b) => a.start - b.start).forEach(change => {
                code.appendChild(document.createTextNode(text.slice(cursor, change.start)));
                const fragment = document.createElement('span');
                fragment.className = 'structural-change-' + kind;
                fragment.textContent = text.slice(change.start, change.end) || change.content;
                fragment.title = 'Columns ' + (change.start + 1) + '–' + change.end;
                code.appendChild(fragment);
                cursor = change.end;
            });
            code.appendChild(document.createTextNode(text.slice(cursor)));
            return code;
        }

        function structuralCell(line, oldNumber, newNumber, changes, kind, dualNumbers) {
            const cell = document.createElement('div');
            cell.className = 'structural-cell';
            cell.appendChild(lineNumber(oldNumber));
            if (dualNumbers) cell.appendChild(lineNumber(newNumber));
            cell.appendChild(codeWithChanges(line, changes, kind));
            return cell;
        }

        function changeMaps(record) {
            const lhs = new Map();
            const rhs = new Map();
            (record.chunks || []).flat().forEach(change => {
                if (change.lhs) lhs.set(change.lhs.line_number, change.lhs.changes || []);
                if (change.rhs) rhs.set(change.rhs.line_number, change.rhs.changes || []);
            });
            return {lhs, rhs};
        }

        function visibleAlignedLines(record, maps) {
            const aligned = record.aligned_lines || [];
            const visible = new Set();
            aligned.forEach((pair, index) => {
                if (maps.lhs.has(pair[0]) || maps.rhs.has(pair[1])) {
                    for (let offset = -3; offset <= 3; offset += 1) {
                        if (index + offset >= 0 && index + offset < aligned.length) visible.add(index + offset);
                    }
                }
            });
            return aligned.map((pair, index) => ({pair, index})).filter(item => visible.has(item.index));
        }

        function fileSection(record, sideBySide) {
            const section = document.createElement('section');
            section.className = 'structural-file';
            const header = document.createElement('div');
            header.className = 'structural-file-header';
            header.textContent = record.path + (record.language ? ' · ' + record.language : '');
            section.appendChild(header);
            const maps = changeMaps(record);
            let previousIndex = -2;
            visibleAlignedLines(record, maps).forEach(({pair, index}) => {
                if (index > previousIndex + 1) {
                    const separator = document.createElement('div');
                    separator.className = 'structural-separator';
                    separator.textContent = '···';
                    section.appendChild(separator);
                }
                previousIndex = index;
                const [lhsNumber, rhsNumber] = pair;
                const lhsChanges = maps.lhs.get(lhsNumber);
                const rhsChanges = maps.rhs.get(rhsNumber);
                const changed = lhsChanges || rhsChanges;
                if (sideBySide) {
                    const row = document.createElement('div');
                    row.className = 'structural-row';
                    row.append(
                        structuralCell(lhsNumber == null ? '' : record.lhsLines[lhsNumber] || '', lhsNumber, null, lhsChanges, 'remove', false),
                        structuralCell(rhsNumber == null ? '' : record.rhsLines[rhsNumber] || '', rhsNumber, null, rhsChanges, 'add', false)
                    );
                    section.appendChild(row);
                } else if (!changed) {
                    const row = document.createElement('div');
                    row.className = 'structural-inline-row';
                    row.appendChild(structuralCell(record.rhsLines[rhsNumber] || record.lhsLines[lhsNumber] || '', lhsNumber, rhsNumber, [], 'context', true));
                    section.appendChild(row);
                } else {
                    if (lhsNumber != null) {
                        const row = document.createElement('div');
                        row.className = 'structural-inline-row';
                        row.appendChild(structuralCell(record.lhsLines[lhsNumber] || '', lhsNumber, null, lhsChanges, 'remove', true));
                        section.appendChild(row);
                    }
                    if (rhsNumber != null) {
                        const row = document.createElement('div');
                        row.className = 'structural-inline-row';
                        row.appendChild(structuralCell(record.rhsLines[rhsNumber] || '', null, rhsNumber, rhsChanges, 'add', true));
                        section.appendChild(row);
                    }
                }
            });
            return section;
        }

        function renderStructuralDiff(records, output, sideBySide) {
            output.replaceChildren(...records.map(record => fileSection(record, sideBySide)));
            if (records.length === 0) output.textContent = 'No Difftastic diff available';
        }

        const jsonPayload = document.getElementById('difftastic-json');
        const inlineOutput = document.getElementById('difftastic-inline-output');
        const sideBySideOutput = document.getElementById('difftastic-side-by-side-output');
        if (jsonPayload && inlineOutput && sideBySideOutput) {
            try {
                const records = parseDifftasticRecords(decodePayload(jsonPayload));
                renderStructuralDiff(records, inlineOutput, false);
                renderStructuralDiff(records, sideBySideOutput, true);
            } catch (error) {
                inlineOutput.textContent = 'Unable to render Difftastic JSON: ' + error.message;
                sideBySideOutput.textContent = inlineOutput.textContent;
            }
        }
    </script>
</body>
</html>
EOF

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
        GIT_EXTERNAL_DIFF="$DIFFTASTIC_WRAPPER" DFT_REPORT_WITH_SOURCES=yes DFT_UNSTABLE=yes DFT_DISPLAY=json DFT_WIDTH="$DIFFTASTIC_WIDTH" git diff "$BASE_REF"
    else
        GIT_EXTERNAL_DIFF="$DIFFTASTIC_WRAPPER" DFT_REPORT_WITH_SOURCES=yes DFT_UNSTABLE=yes DFT_DISPLAY=json DFT_WIDTH="$DIFFTASTIC_WIDTH" git diff "$BASE_REF"..."$COMPARE_REF"
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
