---
name: project-collaboration-rules
description: Use for general coding project work where Codex must follow user-approved implementation planning, project collaboration rules, privacy-safe examples, no duplicated code, configured linting and formatting, post-change checks, correct dependency use, and root-cause-first debugging before fallbacks or workarounds.
---

# Project Collaboration Rules

For coding tasks in this project, follow these rules:

- Before making design decisions, choosing an implementation approach, or deleting/refactoring code, explain the proposed plan and wait for user approval.
- When changes can be split into multiple commits by independent concerns, ask whether the user wants separate commits before committing.
- Do not include `Codex-Session` lines in commit messages.
- Do not put personal private information in code, tests, fixtures, docs, examples, or commit messages. Use placeholders for real emails, phone numbers, addresses, and similar data.
- Avoid duplicated code. Reuse existing helpers and patterns, or introduce a suitable abstraction when it meaningfully reduces duplication.
- Ensure the project has static analysis and formatting configured. After code changes, run the relevant formatter and checks, and report any checks that could not be run.
- Implement the correct solution even when that requires adding an appropriate dependency.

When investigating bugs, regressions, flaky behavior, unexpected output, build errors, test failures, or unclear implementation problems:

- Identify the essential root cause before choosing a fix.
- Add fallbacks, guards, retries, defaults, or workarounds only after deciding they are justified by the root cause.
