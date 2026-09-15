---
name: project-collaboration-rules
description: Use for every coding project task to follow the existing plan autonomously, escalate only when blocked, keep focused commit boundaries, debug root causes first, verify changed surfaces, protect private data, maintain generated files, and choose appropriate dependencies.
---

# Project Collaboration Rules

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

## Root-cause-first debugging

- Reproduce or localize bugs, regressions, flaky behavior, unexpected output, build errors, test failures, crashes, and performance anomalies when practical.
- Identify the first broken assumption or invalid state before choosing a fix.
- Add fallbacks, guards, retries, defaults, or workarounds only after the root cause shows they are justified.
- Prefer removing the bad state or broken assumption over hiding its symptoms.
- Keep necessary workarounds narrow and document the condition that requires them.

## Conditional guidance

- For implementation or debugging work, read [`references/logging.md`](references/logging.md) and apply its diagnostic logging rules.
- After code or CI changes, read [`references/testing-and-verification.md`](references/testing-and-verification.md) and verify the changed surface.
