# Client UI Best Practices Plugin

This Codex plugin provides client UI threading and state-driven rendering guidance. It defines a
platform-independent `Host` boundary that owns observable UI-ready state and asynchronous
business tasks, so feature behavior can be tested without a UI runtime.

## Contents

- `.codex-plugin/plugin.json` declares the plugin.
- `skills/client-ui-best-practices/SKILL.md` defines main-thread boundaries, a `hostScope` confined to an injected custom serial dispatcher, explicit Default/IO switching, state/effect collection, and UI-free Host tests.
- `agents/client-ui-architecture-reviewer.md` reviews state ownership, Host boundaries, scheduling, lifecycle, and testability; the parent waits for its final report before editing or responding.

## Local Marketplace Entry

The repository marketplace registers this plugin as `client-ui-best-practices` at `./plugins/client-ui-best-practices`.
