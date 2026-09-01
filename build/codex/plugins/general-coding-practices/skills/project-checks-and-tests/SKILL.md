---
name: project-checks-and-tests
description: Use after code changes, test changes, CI fixes, or commit preparation to stabilize changed flows, add appropriate test coverage, and run relevant formatters, checks, and tests.
---

# Project Checks And Tests

For implementation work, keep verification tied to the actual changed surface.

## Rules

- Ensure changed code has appropriate test coverage. Add or update focused tests when behavior changes.
- When a behavior change needs end-to-end coverage, first run the complete critical flow manually in the target environment and confirm that it is repeatable and stable. Do not write end-to-end test code until that flow is stable; then add the end-to-end coverage and run it.
- Run the corresponding tests after code changes, preferring the narrowest meaningful test command first.
- When build scripts (Gradle, Makefile, CMakeLists.txt, package.json scripts, etc.) change, run the corresponding build or compilation to verify the scripts still work correctly.
- Run the relevant formatter, lint, typecheck, static analysis, or build checks configured by the project.
- If a relevant check or test cannot be run, report what was skipped and why.
- Do not run unrelated expensive suites by default when a narrower project-supported command gives useful coverage.
