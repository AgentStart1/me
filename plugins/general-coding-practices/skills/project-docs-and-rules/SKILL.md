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

- When using this plugin reveals an actionable bug, missing guidance, or reusable improvement, report it to [storytellerF/me](https://github.com/storytellerF/me/issues). Identify the owning plugin and skill; do not report project-specific problems without evidence that the plugin needs a change. Finish the user's primary task before non-blocking feedback work.
- Before any search or submission, reduce the finding to a privacy-safe summary. Never send raw conversations, private source code, logs, screenshots, credentials, personal identifiers, account data, or private paths/URLs. Use synthetic examples and the minimum non-sensitive environment details needed to explain the problem. If safe disclosure is impossible, keep the finding local.
- Search both open and closed upstream issues using the plugin name and sanitized symptom keywords. Read likely matches and their resolution; do not rely only on title matches. Reuse a matching issue link instead of opening a duplicate. Add a comment only when it supplies materially new, safe evidence and posting is authorized. A closed issue warrants a new report only for a distinct regression or uncovered case, with a link explaining the difference.
- Submit a new issue when no duplicate exists and the user has authorized upstream reporting in the current session or standing instructions. This rule alone does not authorize external posting. Honor existing authorization without asking again; otherwise prepare a sanitized draft for approval.
- Include the plugin/skill and version, observed and expected behavior, a minimal synthetic reproduction or concrete improvement proposal, and relevant duplicate-search results. Use a concise title prefixed with the plugin name.
- If search, authentication, or submission fails, retain the sanitized draft and explain the blocker; do not post without completing duplicate checks. After an uncertain submission result, check for the created issue before retrying. Return the existing or created issue URL, or clearly mark the report as an unsubmitted draft.
