---
name: project-rule-file-maintenance
description: Use when project conventions, workflows, commands, architecture, tests, or agent guidance change and rule files such as AGENTS.md, CLAUDE.md, or .cursorrules may need updates.
---

# Project Rule File Maintenance

Keep project guidance files aligned with the conventions future agents and contributors need.

## Rules

- Look for existing rule files before adding new ones, including `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `.github/copilot-instructions.md`, or local contributor docs.
- Update rule files when a change alters setup commands, test commands, build workflows, architecture conventions, code style expectations, generated files, or agent-specific instructions.
- Keep guidance concise and actionable. Prefer commands, paths, and concrete conventions over broad advice.
- Do not duplicate the same rule across multiple files unless each consumer actually needs it.
- If the project has multiple instruction files, keep their guidance consistent or explain intentional differences.
