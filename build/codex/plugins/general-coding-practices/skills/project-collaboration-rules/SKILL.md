---
name: project-collaboration-rules
description: Use for coding project work to follow collaboration rules for user-approved planning, commit boundaries, privacy-safe examples, maintainable file generation, avoiding duplicated code, keeping large files modular, and choosing appropriate dependencies.
---

# Project Collaboration Rules

For coding tasks in this project, follow these rules:

- Before making design decisions, choosing an implementation approach, or deleting/refactoring code, explain the proposed plan and wait for user approval.
- Treat approval as applying only to the plan that was explicitly explained. Generic instructions such as "continue" do not approve design choices discovered later.
- If inspection, compilation, tests, or static analysis reveals a new choice that changes module boundaries, dependencies, public APIs, data models, or architecture, pause. Explain the options, trade-offs, and recommendation, then wait for fresh approval before changing direction.
- When changes can be split into multiple commits by independent concerns, ask whether the user wants separate commits before committing.
- Whenever plugin content changes, update that plugin's `.codex-plugin/plugin.json` and `.claude-plugin/plugin.json` versions together in the same change. Keep both manifest versions identical, follow the repository's versioning convention, and keep installed marketplace versions aligned with the modified content.
- Do not include session-specific identifiers in commit messages.
- Do not put personal private information in code, tests, fixtures, docs, examples, or commit messages. Use placeholders for real emails, phone numbers, addresses, and similar data.
- Avoid duplicated code. Reuse existing helpers and patterns, or introduce a suitable abstraction when it meaningfully reduces duplication.
- When a script generates a maintained configuration, script, or structured data file, keep the file body in a template and render it by replacing explicit placeholders. Reserve direct writes for short runtime state files and test fixtures.
- When a code file exceeds 1000 lines, split it by feature or responsibility into appropriate separate files instead of continuing to grow the same file.
- Treat names as maintainable design artifacts. As the domain, responsibilities, or public behavior evolve, proactively rename stale, misleading, overly narrow, or ambiguous classes, functions, files, modules, APIs, tests, and documentation so their names describe the current intent. Include necessary reference updates and preserve compatibility only where it is explicitly required.
- Implement the correct solution even when that requires adding an appropriate dependency.
