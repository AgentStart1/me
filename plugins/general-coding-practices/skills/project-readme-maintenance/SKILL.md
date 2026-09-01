---
name: project-readme-maintenance
description: Use when project features, commands, configuration, installation, usage flows, public APIs, plugin lists, package structure, or user-facing behavior change and the README may need updates focused on project information and how to use it.
context: fork
agent: documentation-and-rules-maintainer
---

# Project Readme Maintenance

Keep README files useful for people trying to understand and use the project.

## Rules

- Update README content when user-facing features, installation steps, configuration, commands, plugin lists, package structure, public APIs, examples, or usage flows change.
- Prefer describing what the project is, what it includes, how to install or configure it, and how to use it.
- Do not turn a README into an exhaustive directory tree or file inventory. Mention a path only when it is needed to run a command, configure the project, find a primary entry point, or make a user-facing decision.
- Keep README examples practical and runnable for users, with clear paths, command names, inputs, and expected high-level outcomes.
- Do not use README sections to document internal validation work. Keep test, lint, CI, or verification details in contributor docs, PR descriptions, changelogs, or project rule files unless users need those commands to use the project.
- Remove or update stale README instructions when code, scripts, file paths, or supported workflows change.
- Keep README content concise and scoped to the audience of the repository.
