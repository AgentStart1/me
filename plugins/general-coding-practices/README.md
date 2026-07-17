# General Coding Practices Plugin

This Codex plugin provides focused skills for project collaboration, README maintenance, verification, rule-file maintenance, root-cause-first debugging, and Kotlin project guidance.

## Contents

- `.codex-plugin/plugin.json` declares the plugin.
- `skills/project-collaboration-rules/SKILL.md` contains collaboration, privacy, duplication, and dependency guidance.
- `skills/project-readme-maintenance/SKILL.md` contains guidance for keeping README files focused on project information and usage.
- `skills/project-checks-and-tests/SKILL.md` contains formatter, static-check, and test-coverage guidance.
- `skills/project-rule-file-maintenance/SKILL.md` contains guidance for keeping `AGENTS.md`, `CLAUDE.md`, and similar project instruction files current.
- `skills/root-cause-before-fallback/SKILL.md` contains root-cause-first debugging guidance.
- `skills/kotlin-project-rules/SKILL.md` contains Kotlin coroutine and threading guidance.

## Local Marketplace Entry

This repository includes `.agents/plugins/marketplace.json` with the local plugin entry:

```json
{
  "name": "general-coding-practices",
  "source": {
    "source": "local",
    "path": "./plugins/general-coding-practices"
  },
  "policy": {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL"
  },
  "category": "Developer Tools"
}
```
