---
name: project-docs-and-rules
description: Use when project features, installation, configuration, commands, APIs, workflows, architecture, tests, conventions, or AI guidance change. Keep user documentation in README.md, developer documentation in DEVELOPMENT.md, and AI instructions in AGENTS.md without duplicating content.
---

# Project Docs and Rules

Keep project documentation aligned with current behavior, using one canonical file for each audience:

- `README.md` is for users installing, configuring, and using the project.
- `DEVELOPMENT.md` is for developers building, testing, debugging, or contributing to the project.
- `AGENTS.md` is for AI agents working in the repository.

Do not create or maintain `CLAUDE.md`, `.cursorrules`, or `.github/copilot-instructions.md`. Put generally applicable AI guidance in `AGENTS.md` instead.

## Locate the canonical guidance

- Inspect existing `README.md`, `DEVELOPMENT.md`, and applicable root or nested `AGENTS.md` files before adding documentation.
- Classify each statement by audience and place it in the corresponding canonical file.
- Link between canonical files when another audience needs a pointer; do not copy the same instructions into multiple files.
- When relevant content exists in a deprecated AI instruction file, migrate the unique, still-applicable guidance to the appropriate `AGENTS.md` rather than continuing to maintain both.

## README content

- Update README files when user-facing features, installation, deployment, configuration, supported integrations, examples, or usage flows change.
- Describe what the project is, what it provides, and how users install, configure, and use it.
- Keep examples practical and runnable, with the paths, commands, inputs, and expected high-level outcomes users need.
- Do not put contributor setup, architecture, internal APIs, test commands, lint commands, CI details, repository conventions, or AI instructions in README files.
- Add a concise link to `DEVELOPMENT.md` when contributors need a clear entry point.

## DEVELOPMENT.md content

- Update `DEVELOPMENT.md` when developer setup, architecture, internal or public APIs, build, test, lint, debugging, release, or contribution workflows change.
- Keep commands runnable and document prerequisites, paths, inputs, and expected outcomes that developers need.
- Record project conventions that human contributors need to make correct changes, but keep AI-only operating instructions in `AGENTS.md`.

## AGENTS.md content

- Update the applicable root or nested `AGENTS.md` when AI-specific repository guidance, constraints, generated-file ownership, validation expectations, or collaboration workflows change.
- Keep instructions scoped to the directory tree governed by that `AGENTS.md`; use nested files only when a subtree genuinely needs different guidance.
- Prefer concise commands, paths, decision rules, and concrete conventions over broad advice.
- Keep generated-file ownership and canonical-source instructions explicit.

## Cleanup

- Remove stale paths, commands, integration lists, agent references, and unsupported workflows.
- Preserve useful existing guidance outside the changed scope.
- Verify links, commands, names, file ownership, and cross-file references against the repository after editing.
