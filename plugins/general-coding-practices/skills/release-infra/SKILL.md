---
name: release-infra
description: Handle release packaging, signing, Docker, proxy, and deployment configuration. Use when a task mentions signing, Docker, proxy, release artifacts, deployment, or runtime infrastructure.
context: fork
agent: release-infra-configurator
---

# Release & Infrastructure

Use the smallest delivery workflow that matches the request and keep repository state observable.

## Release and infrastructure work

- Separate build configuration from deployment configuration and verify signing, cache keys, proxy paths, credentials, and runtime identities independently.
- Use local or deterministic fixtures for validation when live services, maps, or external endpoints would make tests unstable.
- Do not modify a live deployment or download large model/runtime artifacts without explicit user scope.
- For failed releases, collect the exact artifact and workflow evidence first; fix the first broken stage rather than adding retries blindly.

## Instructions

Handle the release or infrastructure task. Provide only the task-specific repository state,
target, and relevant artifact or command output; pass a small explicit number of prior turns only when
the task depends on a specific recent decision.

Wait for every delegated agent's required final report before performing dependent
delivery work or returning a final response; do not treat an active agent as completed.
