---
name: github-pr-ci
description: Handle GitHub pull requests, code reviews, and CI workflow issues. Use when a task mentions PRs, reviews, Actions, workflow files, checks, or CI failures.
context: fork
agent: github-pr-ci-maintainer
---

# GitHub PR & CI

Use the smallest delivery workflow that matches the request and keep repository state observable.

## PR and CI work

- Inspect the effective diff and the failing check before changing code or workflow configuration.
- Prefer the narrowest relevant test, formatter, linter, or action validation command.
- Treat runtime-version deprecations as distinct from functional failures; do not rewrite unrelated workflow steps.
- Before posting a PR or review response, summarize the changed files, checks, and unresolved risks.

## Instructions

Handle the PR, review, or CI task. Provide only the task-specific repository state,
target, and relevant artifact or command output; pass a small explicit number of prior turns only when
the task depends on a specific recent decision.

Wait for every delegated agent's required final report before performing dependent
delivery work or returning a final response; do not treat an active agent as completed.
