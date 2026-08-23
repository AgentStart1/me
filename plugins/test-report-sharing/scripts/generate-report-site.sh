#!/usr/bin/env bash
set -euo pipefail

# generate-report-site.sh
# Assembles all artifacts into a static HTML report site
#
# Usage: generate-report-site.sh [--output-dir DIR]

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

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [--output-dir DIR]"
            echo ""
            echo "Assembles all artifacts into a static HTML report site."
            echo ""
            echo "Options:"
            echo "  --output-dir DIR  Output directory for the report site (default: ./test-reports)"
            echo "  --help, -h        Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo "Generating report site..."
echo "Output directory: $OUTPUT_DIR"

# Copy CSS template if it exists
if [[ -f "$PLUGIN_DIR/templates/style.css" ]]; then
    cp "$PLUGIN_DIR/templates/style.css" "$OUTPUT_DIR/" 2>/dev/null || true
fi

# Generate reports section
generate_reports_section() {
    local reports_dir="$OUTPUT_DIR/reports"
    if [[ -d "$reports_dir" ]] && [[ -n "$(ls -A "$reports_dir" 2>/dev/null)" ]]; then
        # Find all report directories (those with index.html)
        local report_count=0
        cat <<EOF
        <div class="section">
            <h2>📊 Reports</h2>
            <div class="report-links">
EOF
        # Check all directories with index.html
        for report_dir in "$reports_dir"/*/; do
            if [[ -d "$report_dir" ]] && [[ -f "$report_dir/index.html" ]]; then
                local report_name
                report_name=$(basename "$report_dir")
                # Format report name: replace - with space, handle common abbreviations
                local display_name
                display_name=$(echo "$report_name" | sed 's/-/ /g')
                # Uppercase common abbreviations
                display_name=$(echo "$display_name" | sed 's/\bE2e\b/E2E/gi; s/\bApi\b/API/gi; s/\bCss\b/CSS/gi; s/\bHtml\b/HTML/gi; s/\bJs\b/JS/gi; s/\bXml\b/XML/gi')
                # Capitalize first letter of each word
                display_name=$(echo "$display_name" | sed 's/\b\(.\)/\u\1/g')
                echo "                <a href=\"reports/$report_name/index.html\" class=\"btn\">$display_name</a>"
                ((report_count++))
            fi
        done

        # Check for standalone index.html in reports root
        if [[ -f "$reports_dir/index.html" ]]; then
            echo "                <a href=\"reports/index.html\" class=\"btn\">Main Report</a>"
            ((report_count++))
        fi

        if [[ $report_count -eq 0 ]]; then
            echo "                <p class=\"no-data\">No reports found</p>"
        fi

        cat <<EOF
            </div>
        </div>
EOF
    else
        cat <<EOF
        <div class="section">
            <h2>📊 Reports</h2>
            <p class="no-data">No reports found. Run your tests first to generate reports.</p>
        </div>
EOF
    fi
}

# Generate diff section
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
    if [[ -d "$diff_dir" ]] && [[ -f "$diff_dir/index.html" ]]; then
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
        else
            cat <<EOF
        <div class="section">
            <h2>📝 Code Diff</h2>
            <a href="diff/index.html" class="btn">View Diff Report</a>
        </div>
EOF
        fi
    else
        cat <<EOF
        <div class="section">
            <h2>📝 Code Diff</h2>
            <p class="no-data">No diff report generated</p>
        </div>
EOF
    fi
}

# Generate main index.html
cat > "$OUTPUT_DIR/index.html" <<EOF
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Report</title>
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
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            text-align: center;
        }
        .header h1 {
            font-size: 2rem;
            margin-bottom: 10px;
        }
        .header p {
            opacity: 0.9;
        }
        .section {
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .section h2 {
            color: #2c3e50;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #eee;
        }
        .no-data {
            color: #999;
            font-style: italic;
        }
        .recordings-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 15px;
        }
        .recording-item {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 10px;
            text-align: center;
        }
        .recording-item video,
        .recording-item img {
            max-width: 100%;
            border-radius: 4px;
            margin-bottom: 10px;
        }
        .recording-item.more {
            display: flex;
            align-items: center;
            justify-content: center;
            color: #666;
            font-size: 1.2rem;
        }
        .insertions {
            color: #27ae60;
            font-weight: bold;
        }
        .deletions {
            color: #e74c3c;
            font-weight: bold;
        }
        .btn {
            display: inline-block;
            background: #3498db;
            color: white;
            padding: 10px 20px;
            border-radius: 4px;
            text-decoration: none;
            margin-top: 10px;
            transition: background 0.3s;
        }
        .btn:hover {
            background: #2980b9;
        }
        ul {
            list-style: none;
            margin-top: 10px;
        }
        li {
            padding: 5px 0;
        }
        li a {
            color: #3498db;
            text-decoration: none;
        }
        li a:hover {
            text-decoration: underline;
        }
        .footer {
            text-align: center;
            padding: 20px;
            color: #666;
            font-size: 0.9rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📋 Test Report</h1>
            <p>Generated on $(date +"%Y-%m-%d %H:%M:%S")</p>
        </div>

$(generate_reports_section)

$(generate_diff_section)

        <div class="footer">
            <p>Generated by test-report-sharing plugin</p>
        </div>
    </div>
</body>
</html>
EOF

echo ""
echo "Report site generated: $OUTPUT_DIR/index.html"
echo ""
echo "To view the report:"
echo "  1. Open $OUTPUT_DIR/index.html in a browser"
echo "  2. Or start a local server: cd $OUTPUT_DIR && python3 -m http.server 8080"
echo "  3. Or use the start-ngrok.sh script to expose via ngrok"
