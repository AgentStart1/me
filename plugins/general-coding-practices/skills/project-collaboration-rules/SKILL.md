---
name: project-collaboration-rules
description: Use for every coding project task to enforce user-approved design and refactoring decisions, explicit commit boundaries, root-cause-first debugging, focused verification, privacy-safe logging and examples, maintainable generated files, appropriate dependencies, and consistent plugin versioning.
---

# Project Collaboration Rules

## Approval and commit boundaries

- Before making any design decision, choosing an implementation approach, deleting code, or refactoring, explain the proposed plan and wait for user approval.
- Treat approval as applying only to the plan explicitly explained. Generic instructions such as "continue" do not approve design choices discovered later.
- If inspection, compilation, tests, or static analysis reveals a new design or refactoring choice, pause, explain the options and recommendation, and obtain fresh approval before changing direction.
- When independent concerns can be separate commits, ask how the user wants them split before committing.
- Do not include session-specific identifiers in commit messages.

## Project integrity

- Whenever plugin content changes, update its `.codex-plugin/plugin.json` and `.claude-plugin/plugin.json` versions together. Keep both versions and descriptions aligned and follow the repository's versioning convention.
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
