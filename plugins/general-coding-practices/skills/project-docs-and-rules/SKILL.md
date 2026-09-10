---
name: project-docs-and-rules
description: Use when project features, commands, configuration, installation, public APIs, workflows, architecture, tests, conventions, or agent guidance change and README or project rule files may need updates. Maintain user-facing README files and contributor or agent guidance such as AGENTS.md, CLAUDE.md, .cursorrules, and copilot instructions without duplicating content.
context: fork
agent: documentation-and-rules-maintainer
---

# Project Docs and Rules

Keep user documentation and project guidance aligned with the behavior and conventions future users, contributors, and agents need.

## Locate the canonical guidance

- Inspect existing README and rule files before adding new documentation.
- Include applicable `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `.github/copilot-instructions.md`, contributor docs, and nested instruction files.
- Identify the audience and canonical source for each rule. Do not duplicate the same guidance unless separate consumers genuinely require it.
- Keep multiple instruction files consistent, or explain intentional platform-specific differences.

## README content

- Update README files when user-facing features, installation, configuration, commands, plugin lists, examples, public APIs, or usage flows change.
- Describe what the project is, what it provides, and how users install, configure, and use it.
- Keep examples practical and runnable, with the paths, commands, inputs, and expected high-level outcomes users need.
- Do not turn a README into an exhaustive directory tree or internal file inventory.
- Keep internal validation, lint, CI, and agent-maintenance details in contributor or rule files unless users need those commands to use the project.

## Project rule files

- Update rule files when setup, test, build, release, generation, or collaboration workflows change.
- Record architecture and code-style conventions only when future contributors or agents need them to make correct changes.
- Prefer concise commands, paths, decision rules, and concrete conventions over broad advice.
- Keep generated-file ownership and canonical-source instructions explicit.

## Cleanup

- Remove stale paths, commands, plugin lists, agent references, and unsupported workflows.
- Preserve useful existing guidance outside the changed scope.
- Verify links, commands, names, and cross-file references against the repository after editing.
