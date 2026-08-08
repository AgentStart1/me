---
name: repository-delivery
description: Coordinate repository synchronization, GitHub pull requests, CI workflow failures, release packaging, signing, proxy, Docker, and deployment changes. Use when a task mentions upstream sync, branches, PRs, Actions, workflow files, release artifacts, signing, deployment, or runtime infrastructure.
---

# Repository Delivery

Use the smallest delivery workflow that matches the request and keep repository state observable.

## Repository and upstream work

- Inspect the current branch, remotes, worktree, and upstream tracking before syncing or rebasing.
- Preserve unrelated user changes and never use destructive reset or checkout operations to resolve a dirty worktree.
- For an upstream sync, fetch first, compare merge bases, rebase or merge only after the intended target is clear, and report conflicts explicitly.
- Do not commit, push, or open a pull request unless the user explicitly requests that external action.

## PR and CI work

- Inspect the effective diff and the failing check before changing code or workflow configuration.
- Prefer the narrowest relevant test, formatter, linter, or action validation command.
- Treat runtime-version deprecations as distinct from functional failures; do not rewrite unrelated workflow steps.
- Before posting a PR or review response, summarize the changed files, checks, and unresolved risks.

## Release and infrastructure work

- Separate build configuration from deployment configuration and verify signing, cache keys, proxy paths, credentials, and runtime identities independently.
- Use local or deterministic fixtures for validation when live services, maps, or external endpoints would make tests unstable.
- Do not modify a live deployment or download large model/runtime artifacts without explicit user scope.
- For failed releases, collect the exact artifact and workflow evidence first; fix the first broken stage rather than adding retries blindly.

## Delegated agents

- Use `../../agents/github-pr-ci-maintainer.md` for PR, review, and Actions work.
- Use `../../agents/repository-sync-agent.md` for branch, upstream, and submodule synchronization.
- Use `../../agents/release-infra-configurator.md` for signing, Docker, proxy, release, and deployment configuration.

Each Markdown agent contains Claude `model`/`effort` frontmatter and a `Codex routing:` line. The
manual installer converts that metadata into top-level Codex `model` and `model_reasoning_effort`
fields in `.toml` agent files. Do not describe the Codex routing as prompt-only guidance.
