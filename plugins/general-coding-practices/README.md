# General Coding Practices Plugin

This Codex plugin provides a skill for project collaboration rules and general coding practices.

## Contents

- `.codex-plugin/plugin.json` declares the plugin.
- `skills/project-collaboration-rules/SKILL.md` contains the project collaboration and coding-practice guidance.

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
