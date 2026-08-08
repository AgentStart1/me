---
name: root-cause-before-fallback
description: Use when investigating bugs, regressions, flaky behavior, unexpected output, build errors, test failures, crashes, performance anomalies, or unclear implementation problems where Codex should identify the root cause before adding fallbacks, guards, retries, defaults, or workarounds.
---

# Root Cause Before Fallback

Fix the underlying problem before adding defensive layers.

## Rules

- Identify the essential root cause before choosing a fix.
- Reproduce or localize the failure when practical, using logs, tests, traces, diffs, or minimal examples.
- Add fallbacks, guards, retries, defaults, or workarounds only after deciding they are justified by the root cause.
- Prefer fixes that remove the bad state or broken assumption over fixes that merely hide the symptom.
- When a workaround is necessary, keep it narrow and document the condition that makes it necessary.

## Delegated agent

When the task spans multiple files, logs, or runtime layers, use `../../agents/root-cause-debugger.md` as
the delegated prompt. Keep the investigation read-only until the failure is localized, then return
the evidence, root cause, smallest safe fix, and focused verification command to the parent agent.
