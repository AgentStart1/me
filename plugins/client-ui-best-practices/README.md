# Client UI Best Practices Plugin

This portable plugin provides client UI threading and state-driven rendering guidance. It defines a
platform-independent `Host` boundary that owns observable UI-ready state and asynchronous
business tasks, so feature behavior can be tested without a UI runtime.

Cancellation remains control flow, and serial dispatchers/actors can interleave
asynchronous requests at suspension points. The examples preserve cancellation and
use request generations to reject superseded completions. Claude agent routing
applies to generated Claude packages; Codex loads the portable skill guidance.

## Project independence

Applying this guidance creates project-owned UI architecture without a dependency on the AI plugin or its agent. Required UI libraries, compiler plugins and build plugins remain normal project dependencies.

## Contents

- `plugin.json` declares the portable plugin and client extensions.
- `skills/client-ui-best-practices/SKILL.md` defines main-thread boundaries, a `hostScope` confined to an injected custom serial dispatcher, explicit Default/IO switching, state/effect collection, and UI-free Host tests.
- `agents/client-ui-architecture-reviewer.md` reviews state ownership, Host boundaries, scheduling, lifecycle, and testability; the parent waits for its final report before editing or responding.

## Local Marketplace Entry

The repository marketplace registers this plugin as `client-ui-best-practices` at `./plugins/client-ui-best-practices`.

## Plugin packaging

`plugin.json` is the portable metadata source. Client manifests and complete skill resources are generated into `me.claude` and `me.codex`; install from those repositories. Source skills use portable frontmatter. Claude routing is stored in `extensions.com.anthropic.claude.skillFrontmatter`, keyed by skill directory, and injected only into generated Claude skills. Codex skill files are copied unchanged.

## Improvement feedback

Plugin findings go to [storytellerF/me issues](https://github.com/storytellerF/me/issues). Skills require checking open and closed issues before reporting, using sanitized or synthetic examples, and honoring the user's authorization before posting. Existing reports are reused; unavailable access leaves an unsubmitted draft.
