---
name: project-collaboration-rules
description: Use for coding project work where Codex must follow collaboration rules for user-approved planning, commit boundaries, privacy-safe examples, avoiding duplicated code, and choosing appropriate dependencies.
---

# Project Collaboration Rules

For coding tasks in this project, follow these rules:

- Before making design decisions, choosing an implementation approach, or deleting/refactoring code, explain the proposed plan and wait for user approval.
- When changes can be split into multiple commits by independent concerns, ask whether the user wants separate commits before committing.
- Do not include `Codex-Session` lines in commit messages.
- Do not put personal private information in code, tests, fixtures, docs, examples, or commit messages. Use placeholders for real emails, phone numbers, addresses, and similar data.
- Avoid duplicated code. Reuse existing helpers and patterns, or introduce a suitable abstraction when it meaningfully reduces duplication.
- Implement the correct solution even when that requires adding an appropriate dependency.
