#!/usr/bin/env bash
set -uo pipefail

# collect-test-results.sh
# Collects test results from standard project locations
#
# Usage: collect-test-results.sh [--output-dir DIR] [--test-dirs DIR:DIR:...]

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
TEST_RESULT_DIRS="${TEST_RESULT_DIRS:-}"
BASE_REF="${GIT_BASE_REF:-main}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --test-dirs)
            TEST_RESULT_DIRS="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [--output-dir DIR] [--test-dirs DIR:DIR:...]"
            echo ""
            echo "Collects test results from standard project locations."
            echo ""
            echo "Options:"
            echo "  --output-dir DIR    Output directory for collected results (default: ./test-reports)"
            echo "  --test-dirs DIRS    Colon-separated list of directories to scan"
            echo "  --help, -h          Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# Create output directory
mkdir -p "$OUTPUT_DIR/reports"

# Function to collect a complete test report directory
collect_test_report() {
    local report_dir="$1"
    local report_name="$2"
    local target_dir="$OUTPUT_DIR/reports/$report_name"

    if [[ ! -d "$report_dir" ]]; then
        return 0
    fi

    mkdir -p "$target_dir"
    cp -r "$report_dir"/* "$target_dir/" 2>/dev/null || true

    # Check if index.html references ../css/ or ../js/ and copy those if needed
    if [[ -f "$target_dir/index.html" ]]; then
        local parent_dir
        parent_dir=$(dirname "$report_dir")

        # Copy CSS files if referenced
        if grep -q '\.\./css/' "$target_dir/index.html" 2>/dev/null && [[ -d "$parent_dir/css" ]]; then
            mkdir -p "$target_dir/css"
            cp -r "$parent_dir/css"/* "$target_dir/css/" 2>/dev/null || true
            # Fix CSS references in HTML
            sed -i 's|href="../css/|href="css/|g' "$target_dir/index.html"
        fi

        # Copy JS files if referenced
        if grep -q '\.\./js/' "$target_dir/index.html" 2>/dev/null && [[ -d "$parent_dir/js" ]]; then
            mkdir -p "$target_dir/js"
            cp -r "$parent_dir/js"/* "$target_dir/js/" 2>/dev/null || true
            # Fix JS references in HTML
            sed -i 's|src="../js/|src="js/|g' "$target_dir/index.html"
        fi
    fi

    # Find the index.html in the copied report
    if [[ -f "$target_dir/index.html" ]]; then
        echo "$target_dir"
    else
        echo ""
    fi
}

# Build search directories list
declare -a search_dirs=()

# Add default locations
default_dirs=(
    "./build/reports"
    "./app/build/reports"
    "./androidApp/build/reports"
    "./shared/build/reports"
    "./target/surefire-reports"
    "./target/failsafe-reports"
    "./test-results"
    "./test-reports"
    "./reports"
)

for dir in "${default_dirs[@]}"; do
    if [[ -d "$dir" ]]; then
        search_dirs+=("$dir")
    fi
done

# Add custom directories from environment
if [[ -n "$TEST_RESULT_DIRS" ]]; then
    IFS=':' read -ra custom_dirs <<< "$TEST_RESULT_DIRS"
    for dir in "${custom_dirs[@]}"; do
        if [[ -d "$dir" ]]; then
            search_dirs+=("$dir")
        fi
    done
fi

echo "Collecting reports..."
echo "Output directory: $OUTPUT_DIR/reports"
echo "Search directories: ${search_dirs[*]}"

# Find and collect all test report directories
declare -a report_dirs=()
declare -a collected_dirs=()
total_reports=0

# Find all index.html files in the search directories
for dir in "${search_dirs[@]}"; do
    if [[ ! -d "$dir" ]]; then
        continue
    fi

    # Find index.html files in this directory (search deeper)
    while IFS= read -r index_file; do
        if [[ -f "$index_file" ]]; then
            report_dir=$(dirname "$index_file")
            # Skip if this directory or a parent was already collected
            skip=false
            for collected in "${collected_dirs[@]}"; do
                if [[ "$report_dir" == "$collected" ]] || [[ "$collected" == "$report_dir/"* ]]; then
                    skip=true
                    break
                fi
            done
            if [[ "$skip" == "true" ]]; then
                continue
            fi

            # Collect if this directory has index.html
            report_name="report-${total_reports}"
            result=$(collect_test_report "$report_dir" "$report_name")
            if [[ -n "$result" ]]; then
                report_dirs+=("$result")
                collected_dirs+=("$report_dir")
                ((total_reports++))
                echo "  Collected report: $report_dir -> $report_name"
            fi
        fi
    done < <(find "$dir" -maxdepth 4 -name "index.html" 2>/dev/null || true)
done

# Also collect standalone XML files
xml_count=0
for dir in "${search_dirs[@]}"; do
    if [[ -d "$dir" ]]; then
        while IFS= read -r -d '' file; do
            cp "$file" "$OUTPUT_DIR/test-results/" 2>/dev/null || true
            ((xml_count++))
        done < <(find "$dir" -maxdepth 1 -type f \( -name "*-tests.xml" -o -name "TEST-*.xml" \) -print0 2>/dev/null || true)
    fi
done

echo ""
echo "Collection complete:"
echo "  Test reports found: $total_reports"
echo "  Standalone XML files: $xml_count"

# Generate summary file
cat > "$OUTPUT_DIR/reports/summary.json" <<EOF
{
  "collection_time": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "total_reports": $total_reports,
  "xml_files": $xml_count,
  "report_directories": $(printf '%s\n' "${report_dirs[@]}" | jq -R . | jq -s .)
}
EOF

echo ""
echo "Summary written to: $OUTPUT_DIR/reports/summary.json"

if [[ $total_reports -eq 0 ]] && [[ $xml_count -eq 0 ]]; then
    echo ""
    echo "Warning: No test results found. Check your test configuration and output directories."
fi