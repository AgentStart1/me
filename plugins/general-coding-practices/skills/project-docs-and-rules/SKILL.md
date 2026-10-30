---
name: project-docs-and-rules
description: Use when maintaining project documentation or AI guidance, or when changes affect documented behavior, setup, commands, APIs, workflows, or conventions. Internal-only changes do not automatically require documentation edits.
---

# Project Docs and Rules

Check whether the change affects documented behavior or guidance before editing documentation. Internal-only changes need no documentation churn when the existing guidance remains accurate.

Keep project documentation aligned with current behavior, using one canonical file for each audience:

- `README.md` is for users installing, configuring, and using the project.
- `DEVELOPMENT.md` is for developers building, testing, debugging, or contributing to the project.
- `AGENTS.md` is for AI agents working in the repository.

Do not create or maintain `CLAUDE.md`, `.cursorrules`, or `.github/copilot-instructions.md`. Put generally applicable AI guidance in `AGENTS.md` instead.

## Project independence

Document the project's supported tools, normal commands, endpoints and portable configuration. Do not write AI-plugin installation paths, cache versions, orchestration helpers, provider-specific environment switches or operator maintenance procedures into a consuming project's README, DEVELOPMENT.md or AGENTS.md merely because a skill was used. Keep those instructions in the owning AI plugin or operator environment. This also applies when saving newly learned project rules.

Preserve documentation for actual project dependencies such as Gradle plugins and Appium drivers/extensions, including required versions and setup. These are distinct from AI assistant plugins. When the user explicitly requests AI-plugin integration, document only that requested scope; the AI plugin's own repository may describe its implementation and installation normally.

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

## Upstream improvement feedback

- Report actionable plugin bugs or reusable improvements to [storytellerF/me](https://github.com/storytellerF/me/issues), identifying the plugin and skill. Exclude project-only problems without evidence of a plugin defect. Finish the primary task before non-blocking feedback work.
- Before searching or posting, reduce evidence to a minimal privacy-safe summary or synthetic reproduction. Never disclose raw conversations, private code, logs, screenshots, credentials, personal/account data, or private paths/URLs. Keep findings local if safe disclosure is impossible.
- Search open and closed issues and read likely matches and resolutions. Reuse matching reports; a distinct regression or uncovered case may need a linked new issue. Posting a new issue or a materially useful comment requires existing user authorization; this rule grants none. Without authorization, prepare an unsubmitted draft.
- Include the plugin/skill version, observed and expected behavior, reproduction or proposal, and duplicate-search results; prefix new issue titles with the plugin name. On access or submission failure, retain the draft and explain the blocker. After an uncertain submission, check whether it succeeded before retrying. Return the report link or clearly label the draft as unsubmitted.
