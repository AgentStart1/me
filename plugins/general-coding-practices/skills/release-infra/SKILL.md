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
