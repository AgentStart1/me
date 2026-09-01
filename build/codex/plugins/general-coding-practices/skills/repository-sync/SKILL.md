---
name: repository-sync
description: Synchronize branches, upstream changes, and submodules. Use when a task mentions upstream sync, branches, rebasing, merging, or submodule synchronization.
---

# Repository Sync

Use the smallest delivery workflow that matches the request and keep repository state observable.

## Repository and upstream work

- Inspect the current branch, remotes, worktree, and upstream tracking before syncing or rebasing.
- Preserve unrelated user changes and never use destructive reset or checkout operations to resolve a dirty worktree.
- For an upstream sync, fetch first, compare merge bases, rebase or merge only after the intended target is clear, and report conflicts explicitly.
- After an upstream PR is merged, sync the local main branch to match upstream main before starting new work.
- Do not commit, push, or open a pull request unless the user explicitly requests that external action.
