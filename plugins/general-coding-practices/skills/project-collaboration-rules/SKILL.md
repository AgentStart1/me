---
name: project-collaboration-rules
description: Use for every coding project task to follow the existing plan autonomously, escalate only when blocked, keep focused commit boundaries, debug root causes first, verify changed surfaces, protect private data, maintain generated files, and choose appropriate dependencies.
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

- When using this plugin reveals an actionable bug, missing guidance, or reusable improvement, report it to [storytellerF/me](https://github.com/storytellerF/me/issues). Identify the owning plugin and skill; do not report project-specific problems without evidence that the plugin needs a change. Finish the user's primary task before non-blocking feedback work.
- Before any search or submission, reduce the finding to a privacy-safe summary. Never send raw conversations, private source code, logs, screenshots, credentials, personal identifiers, account data, or private paths/URLs. Use synthetic examples and the minimum non-sensitive environment details needed to explain the problem. If safe disclosure is impossible, keep the finding local.
- Search both open and closed upstream issues using the plugin name and sanitized symptom keywords. Read likely matches and their resolution; do not rely only on title matches. Reuse a matching issue link instead of opening a duplicate. Add a comment only when it supplies materially new, safe evidence and posting is authorized. A closed issue warrants a new report only for a distinct regression or uncovered case, with a link explaining the difference.
- Submit a new issue when no duplicate exists and the user has authorized upstream reporting in the current session or standing instructions. This rule alone does not authorize external posting. Honor existing authorization without asking again; otherwise prepare a sanitized draft for approval.
- Include the plugin/skill and version, observed and expected behavior, a minimal synthetic reproduction or concrete improvement proposal, and relevant duplicate-search results. Use a concise title prefixed with the plugin name.
- If search, authentication, or submission fails, retain the sanitized draft and explain the blocker; do not post without completing duplicate checks. After an uncertain submission result, check for the created issue before retrying. Return the existing or created issue URL, or clearly mark the report as an unsubmitted draft.
