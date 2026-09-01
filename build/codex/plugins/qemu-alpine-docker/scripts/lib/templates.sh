# Literal placeholder rendering for maintained provisioning templates.
# Sourced by ../vm-utils.sh; this module has no dependency on other modules.

render_template() (
    local template_path="$1" output_path="$2"
    shift 2
    [ -f "$template_path" ] || {
        echo "Error: Template not found: ${template_path}." >&2
        return 1
    }
    [ $(( $# % 2 )) -eq 0 ] || {
        echo "Error: Template replacements must be NAME/value pairs." >&2
        return 1
    }

    local content placeholder value output_dir temp_path
    content="$(<"$template_path")"
    shopt -u patsub_replacement 2>/dev/null || true
    while [ "$#" -gt 0 ]; do
        placeholder="{{${1}}}"
        value="$2"
        [[ "$content" == *"$placeholder"* ]] || {
            echo "Error: Placeholder ${placeholder} is missing from ${template_path}." >&2
            return 1
        }
        content="${content//"$placeholder"/"$value"}"
        shift 2
    done
    if [[ "$content" =~ \{\{[A-Z][A-Z0-9_]*\}\} ]]; then
        echo "Error: Unresolved placeholder ${BASH_REMATCH[0]} in ${template_path}." >&2
        return 1
    fi

    output_dir="$(dirname "$output_path")"
    mkdir -p "$output_dir"
    temp_path="${output_path}.tmp.${BASHPID:-$$}"
    printf '%s\n' "$content" > "$temp_path"
    mv "$temp_path" "$output_path"
)
