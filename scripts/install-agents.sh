#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf '%s\n' \
    'Usage: scripts/install-agents.sh [--target codex|claude|both] [--scope global|project]' \
    '       [--project-dir PATH] [--dry-run]'
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
    agent_name="$(basename "$prompt_file")"
    destination="$destination_root/$agent_name"
    printf '%s -> %s\n' "$prompt_file" "$destination"
    if [[ "$dry_run" != true ]]; then
      mkdir -p "$destination_root"
      install -m 0644 "$prompt_file" "$destination"
    fi
  done
done
