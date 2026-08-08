#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf '%s\n' \
    'Usage: scripts/install-agents.sh [--target codex|claude|both] [--scope global|project]' \
    '       [--project-dir PATH] [--dry-run]'
}

yaml_field() {
  local field_name="$1"
  local prompt_file="$2"

  awk -v field_name="$field_name" '
    NR == 1 && $0 == "---" { in_frontmatter = 1; next }
    in_frontmatter && $0 == "---" { exit }
    in_frontmatter && $0 ~ "^" field_name ":[[:space:]]*" {
      sub("^" field_name ":[[:space:]]*", "")
      print
      exit
    }
  ' "$prompt_file"
}

toml_quote() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '"%s"' "$value"
}

render_codex_agent() {
  local prompt_file="$1"
  local destination="$2"
  local name description routing_line model reasoning_effort developer_instructions

  name="$(yaml_field name "$prompt_file")"
  description="$(yaml_field description "$prompt_file")"
  routing_line="$(awk '/^Codex routing: / { print; exit }' "$prompt_file")"
  model="$(printf '%s\n' "$routing_line" | sed -n 's/^Codex routing: `\([^`]*\)` with `reasoning_effort: \([^`]*\)`.*/\1/p')"
  reasoning_effort="$(printf '%s\n' "$routing_line" | sed -n 's/^Codex routing: `\([^`]*\)` with `reasoning_effort: \([^`]*\)`.*/\2/p')"
  developer_instructions="$(awk '
    NR == 1 && $0 == "---" { in_frontmatter = 1; next }
    in_frontmatter && $0 == "---" { in_frontmatter = 0; next }
    !in_frontmatter && $0 !~ /^Codex routing: / { print }
  ' "$prompt_file")"

  if [[ -z "$name" || -z "$description" || -z "$model" || -z "$reasoning_effort" ]]; then
    printf 'Missing Codex metadata in %s\n' "$prompt_file" >&2
    exit 1
  fi
  if [[ "$developer_instructions" == *'"""'* ]]; then
    printf 'Unsupported triple-quote sequence in %s\n' "$prompt_file" >&2
    exit 1
  fi

  mkdir -p "$(dirname -- "$destination")"
  {
    printf 'name = %s\n' "$(toml_quote "$name")"
    printf 'description = %s\n' "$(toml_quote "$description")"
    printf 'model = %s\n' "$(toml_quote "$model")"
    printf 'model_reasoning_effort = %s\n' "$(toml_quote "$reasoning_effort")"
    printf 'developer_instructions = """\n'
    printf '%s\n' "$developer_instructions"
    printf '"""\n'
  } > "$destination"
}

target_kind="codex"
scope_kind="global"
project_dir="$(pwd)"
dry_run="false"

while (($# > 0)); do
  case "$1" in
    --target)
      target_kind="${2:?missing value for --target}"
      shift 2
      ;;
    --scope)
      scope_kind="${2:?missing value for --scope}"
      shift 2
      ;;
    --project-dir)
      project_dir="${2:?missing value for --project-dir}"
      shift 2
      ;;
    --dry-run)
      dry_run="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

case "$target_kind" in
  codex|claude|both) ;;
  *) printf 'Invalid --target: %s\n' "$target_kind" >&2; exit 2 ;;
esac
case "$scope_kind" in
  global|project) ;;
  *) printf 'Invalid --scope: %s\n' "$scope_kind" >&2; exit 2 ;;
esac

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "$script_dir/.." && pwd)"
codex_home="${CODEX_HOME:-$HOME/.codex}"

case "$scope_kind:$target_kind" in
  global:codex) destination_roots=("$codex_home/agents") ;;
  global:claude) destination_roots=("$HOME/.claude/agents") ;;
  global:both) destination_roots=("$codex_home/agents" "$HOME/.claude/agents") ;;
  project:codex) destination_roots=("$project_dir/.codex/agents") ;;
  project:claude) destination_roots=("$project_dir/.claude/agents") ;;
  project:both) destination_roots=("$project_dir/.codex/agents" "$project_dir/.claude/agents") ;;
esac

mapfile -t prompt_files < <(
  find "$repo_dir/agents" "$repo_dir/plugins" \
    -type f -path '*/agents/*.md' -print 2>/dev/null | sort
)

if ((${#prompt_files[@]} == 0)); then
  printf 'No agent prompts found under %s\n' "$repo_dir" >&2
  exit 1
fi

for destination_root in "${destination_roots[@]}"; do
  for prompt_file in "${prompt_files[@]}"; do
    prompt_name="$(basename "$prompt_file")"
    if [[ "$destination_root" == */.codex/agents ]]; then
      destination="$destination_root/${prompt_name%.md}.toml"
      printf '%s -> %s (generated Codex TOML)\n' "$prompt_file" "$destination"
    else
      destination="$destination_root/$prompt_name"
      printf '%s -> %s (Claude Markdown)\n' "$prompt_file" "$destination"
    fi
    if [[ "$dry_run" != true ]]; then
      if [[ "$destination_root" == */.codex/agents ]]; then
        render_codex_agent "$prompt_file" "$destination"
        chmod 0644 "$destination"
      else
        mkdir -p "$destination_root"
        install -m 0644 "$prompt_file" "$destination"
      fi
    fi
  done
done
