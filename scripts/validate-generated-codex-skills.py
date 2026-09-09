#!/usr/bin/env python3
"""Validate every generated Codex skill using the skill-creator quick checks."""

import re
import sys
from pathlib import Path

import yaml


ALLOWED_FRONTMATTER_KEYS = {"name", "description", "license", "allowed-tools", "metadata"}


def validate_skill(skill_path: Path) -> list[str]:
    skill_file = skill_path / "SKILL.md"
    if not skill_file.is_file():
        return ["SKILL.md not found"]

    content = skill_file.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return ["invalid or missing YAML frontmatter"]

    try:
        frontmatter = yaml.safe_load(match.group(1))
    except yaml.YAMLError as error:
        return [f"invalid YAML frontmatter: {error}"]

    if not isinstance(frontmatter, dict):
        return ["frontmatter must be a YAML dictionary"]

    errors = []
    unexpected = set(frontmatter) - ALLOWED_FRONTMATTER_KEYS
    if unexpected:
        errors.append(f"unexpected frontmatter keys: {', '.join(sorted(unexpected))}")

    name = frontmatter.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        errors.append("name must be a lowercase hyphen-case string")
    elif len(name) > 64:
        errors.append("name exceeds 64 characters")

    description = frontmatter.get("description")
    if not isinstance(description, str):
        errors.append("description must be a string")
    elif description.startswith("[TODO:") or "<" in description or ">" in description or len(description) > 1024:
        errors.append("description is incomplete or invalid")

    in_fence = None
    for line in content[match.end() :].splitlines():
        fence = re.match(r"^[ \t]*(?:[-+*]|\d+[.)])?[ \t]*(`{3,}|~{3,})(.*)$", line)
        if fence:
            marker, suffix = fence.groups()
            if in_fence is None:
                in_fence = marker[0], len(marker)
            elif marker[0] == in_fence[0] and len(marker) >= in_fence[1] and not suffix.strip():
                in_fence = None
        elif in_fence is None and re.fullmatch(r"[ ]{0,3}\[TODO:[^\n]*\][ \t]*", line):
            errors.append("instructions contain an unfinished TODO")
            break

    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {Path(sys.argv[0]).name} <generated-plugins-directory>", file=sys.stderr)
        return 1

    plugins_directory = Path(sys.argv[1])
    failures = []
    for skill_file in sorted(plugins_directory.glob("*/skills/*/SKILL.md")):
        errors = validate_skill(skill_file.parent)
        if errors:
            failures.append(f"{skill_file}: {'; '.join(errors)}")

    if failures:
        print("Generated Codex skill validation failed:", *failures, sep="\n", file=sys.stderr)
        return 1

    print("Generated Codex skills are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
