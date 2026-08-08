---
name: project-readme-maintenance
description: Use when project features, commands, configuration, installation, usage flows, public APIs, plugin lists, package structure, or user-facing behavior change and the README may need updates focused on project information and how to use it.
---

# Project Readme Maintenance

Keep README files useful for people trying to understand and use the project.

## Rules

- Update README content when user-facing features, installation steps, configuration, commands, plugin lists, package structure, public APIs, examples, or usage flows change.
- Prefer describing what the project is, what it includes, how to install or configure it, and how to use it.
- Keep README examples practical and runnable for users, with clear paths, command names, inputs, and expected high-level outcomes.
- Do not use README sections to document internal validation work. Keep test, lint, CI, or verification details in contributor docs, PR descriptions, changelogs, or project rule files unless users need those commands to use the project.
- Remove or update stale README instructions when code, scripts, file paths, or supported workflows change.
- Keep README content concise and scoped to the audience of the repository.

## Delegated agent

Use `agents/documentation-and-rules-maintainer.md` when a feature, plugin, installation flow, or
agent workflow changes several user-facing files. Keep implementation details in rules or skill
files and keep README content focused on what the project contains and how users operate it.
