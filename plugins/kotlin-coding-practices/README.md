# Kotlin Coding Practices Plugin

This plugin provides focused Kotlin and Android Kotlin guidance for structured concurrency,
coroutine-friendly synchronization, immutable values, and explicit boundaries around platform APIs
that require Java threading or blocking behavior.

## Contents

- `plugin.json` declares the portable plugin; client manifests are generated.
- `skills/kotlin-project-rules/SKILL.md` contains Kotlin coroutine, threading, synchronization, cancellation, lifecycle, immutability, and KDoc contract guidance.

## Local Marketplace Entry

The repository marketplaces register this plugin as `kotlin-coding-practices` at
`./plugins/kotlin-coding-practices`.

## Plugin packaging

`plugin.json` is the portable metadata source. Client manifests and complete skill resources are generated into `me.claude` and `me.codex`; install from those repositories. Source skills use portable frontmatter. Claude routing is stored in `extensions.com.anthropic.claude.skillFrontmatter`, keyed by skill directory, and injected only into generated Claude skills. Codex skill files are copied unchanged.
