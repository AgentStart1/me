---
name: project-checks-and-tests
description: Use after code changes, test changes, CI fixes, or commit preparation when Codex should ensure test coverage and run relevant formatters, checks, and tests.
context: fork
agent: test-verification-agent
---

# Project Checks And Tests

For implementation work, keep verification tied to the actual changed surface.

## Rules

- Ensure changed code has appropriate test coverage. Add or update focused tests when behavior changes.
- Run the corresponding tests after code changes, preferring the narrowest meaningful test command first.
- Run the relevant formatter, lint, typecheck, static analysis, or build checks configured by the project.
- If a relevant check or test cannot be run, report what was skipped and why.
- Do not run unrelated expensive suites by default when a narrower project-supported command gives useful coverage.
