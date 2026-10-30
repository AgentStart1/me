---
name: project-collaboration-rules
description: Use for coding-project work, including implementation, debugging, review, testing, and maintenance, to apply collaboration, change-scope, privacy, and verification rules.
---

# Project Collaboration Rules

## Project independence

- Using an AI plugin or skill must not make the target project depend on that assistant's tooling. Do not add AI-plugin names, installation/cache paths, helper invocations, provider-specific flags or branches, or plugin maintenance instructions to project code, build/CI configuration, documentation, or AGENTS.md merely because the plugin was used.
- Keep AI-plugin orchestration, private connection profiles, credentials and temporary ownership state in the operator environment. Use the project's existing commands, standard protocols/endpoints and portable configuration for real project requirements. Project behavior and documented commands must remain usable without installing this AI plugin.
- Normal project dependencies remain valid: declare and document required Gradle plugins, Appium drivers/extensions, compiler plugins, libraries and their configuration. Distinguish these from the AI plugin that arranged their use; do not remove a legitimate dependency because it is called a plugin.
- An explicit request to integrate an AI plugin permits the requested coupling only. Document its scope and keep ordinary project workflows independent where possible. This rule does not prevent maintaining an AI plugin's own implementation, documentation or explicitly requested agent guidance.

## Execution and commit boundaries

- Follow the existing plan within the user's requested scope, making routine implementation decisions and resolving issues autonomously. Do not ask the user merely because a problem or new implementation detail appears.
- Ask the user only when an issue prevents further progress under the existing plan and no safe, reasonable plan-consistent path remains. Explain the blocker, the attempted resolution, and the decision or information needed to continue.
- When committing is within the requested scope, split independent concerns into focused commits using the project's conventions and any user-specified boundaries.
- Do not include session-specific identifiers in commit messages.

## Project integrity

- Do not put personal private information in code, tests, fixtures, documentation, examples, or commit messages. Use placeholders for real emails, phone numbers, addresses, and similar data.
- Avoid duplicated code. Reuse existing helpers and patterns, or introduce an abstraction when it meaningfully reduces duplication.
- When a script generates a maintained configuration, script, or structured data file, keep the body in a template and render explicit placeholders. Reserve direct writes for short runtime state files and test fixtures.
- Split code files that exceed 1000 lines by feature or responsibility instead of continuing to grow the same file.
- Rename stale, misleading, overly narrow, or ambiguous classes, functions, files, modules, APIs, tests, and documentation when responsibilities or public behavior change. Preserve compatibility only where explicitly required.
- Implement the correct solution even when it requires an appropriate dependency.

## Comments and API documentation

- Prefer clear names and small, well-structured code before adding comments. Do not narrate obvious statements or repeat what the code already expresses.
- Explain non-obvious reasons, business constraints, design tradeoffs, compatibility limits, and required execution order. Place the explanation near the code it governs.
- Document contracts that callers cannot infer: units, valid ranges, ownership, lifecycle, concurrency requirements, and failure behavior.
- For necessary workarounds, explain the triggering condition, link the relevant issue or authoritative reference when available, and state when the workaround can be removed.
- Add API documentation where public APIs or complex contracts need it; do not require boilerplate comments for every internal function.
- Update or remove comments when behavior changes. Remove commented-out obsolete code; use version control for history.
- Make TODOs actionable by stating the remaining work and completion condition, with an issue link when available.
- Follow the project's established comment language and documentation style, and keep comments privacy-safe.

## Root-cause-first debugging

- Reproduce or localize bugs, regressions, flaky behavior, unexpected output, build errors, test failures, crashes, and performance anomalies when practical.
- Identify the first broken assumption or invalid state before choosing a fix.
- Add fallbacks, guards, retries, defaults, or workarounds only after the root cause shows they are justified.
- Prefer removing the bad state or broken assumption over hiding its symptoms. For ownership, lifecycle, or boundary problems, follow the structural-fix guidance in [code-design-rules](../code-design-rules/SKILL.md) before adding compensating patches.
- Keep necessary workarounds narrow and document the condition that requires them.

## Conditional guidance

- For implementation or debugging work, read [`references/logging.md`](references/logging.md) and apply its diagnostic logging rules.
- After code or CI changes, read [`references/testing-and-verification.md`](references/testing-and-verification.md) and verify the changed surface.
- When adding, modifying, refactoring, or reviewing tests (including code reviews involving tests and test-quality reviews), read the same testing reference and check test names, assertions, and overloaded scenarios. Focus ordinary changes on new and affected tests; expand to a repository-wide audit only when requested.

## Upstream improvement feedback

- Report actionable plugin bugs or reusable improvements to [storytellerF/me](https://github.com/storytellerF/me/issues), identifying the plugin and skill. Exclude project-only problems without evidence of a plugin defect. Finish the primary task before non-blocking feedback work.
- Before searching or posting, reduce evidence to a minimal privacy-safe summary or synthetic reproduction. Never disclose raw conversations, private code, logs, screenshots, credentials, personal/account data, or private paths/URLs. Keep findings local if safe disclosure is impossible.
- Search open and closed issues and read likely matches and resolutions. Reuse matching reports; a distinct regression or uncovered case may need a linked new issue. Posting a new issue or a materially useful comment requires existing user authorization; this rule grants none. Without authorization, prepare an unsubmitted draft.
- Include the plugin/skill version, observed and expected behavior, reproduction or proposal, and duplicate-search results; prefix new issue titles with the plugin name. On access or submission failure, retain the draft and explain the blocker. After an uncertain submission, check whether it succeeded before retrying. Return the report link or clearly label the draft as unsubmitted.
