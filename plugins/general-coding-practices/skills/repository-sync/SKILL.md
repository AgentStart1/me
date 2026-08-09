---
name: repository-sync
description: Synchronize branches, upstream changes, and submodules. Use when a task mentions upstream sync, branches, rebasing, merging, or submodule synchronization.
context: fork
agent: repository-sync-agent
---

# Repository Sync

Use the smallest delivery workflow that matches the request and keep repository state observable.

## Repository and upstream work

- Inspect the current branch, remotes, worktree, and upstream tracking before syncing or rebasing.
- Preserve unrelated user changes and never use destructive reset or checkout operations to resolve a dirty worktree.
- For an upstream sync, fetch first, compare merge bases, rebase or merge only after the intended target is clear, and report conflicts explicitly.
- Do not commit, push, or open a pull request unless the user explicitly requests that external action.

## Instructions

Handle the repository sync task. Provide only the task-specific repository state,
target, and relevant artifact or command output; pass a small explicit number of prior turns only when
the task depends on a specific recent decision.

Wait for every delegated agent's required final report before performing dependent
delivery work or returning a final response; do not treat an active agent as completed.
