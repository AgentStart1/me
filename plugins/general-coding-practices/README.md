# General Coding Practices Plugin

This plugin provides project collaboration rules plus focused README and project-guidance maintenance. The plugin root also contains a portable Claude-compatible documentation agent prompt.

## Included guidance

- Project collaboration that follows the existing plan autonomously and asks for user input only when a blocker prevents further progress, plus privacy, dependency, generated-file, and focused commit practices.
- Root-cause-first debugging that prefers structural ownership, lifecycle and boundary fixes over accumulating patches, while preserving necessary recovery and privacy-safe diagnostics.
- Comments that explain intent and constraints, document useful API contracts, and keep workarounds and TODOs actionable.
- Focused test, formatter, lint, static-analysis, and build verification.
- Audience-specific documentation maintenance: user guidance in `README.md`, developer guidance in `DEVELOPMENT.md`, and AI guidance in `AGENTS.md`.
- Cross-platform code design rules: sequential async control flow and callback/listener adaptation, plus owned asynchronous work, cancellation, immutable variants, explicit transitions, and rejection of superseded results.
- Portable Claude documentation-agent delegation.

When a skill delegates to a bundled Claude agent, the parent waits for its required final report
before dependent work or its final response.

## Code design guidance

The `code-design-rules` skill covers readable control flow, callback/listener adaptation, state modeling, and
concurrency. It provides shared principles and loads only
relevant platform references: Kotlin/Android, Swift, TypeScript/JavaScript,
Python/asyncio, Rust, and C#/.NET. Each reference maps the principles to native
APIs, state types, documentation conventions, and verification practices.

This replaces `kotlin-coding-practices` and its `kotlin-project-rules` skill.
After updating the marketplace, install or update `general-coding-practices` and
remove the retired Kotlin plugin using your client's plugin manager. Update any
explicit skill references to `code-design-rules`. Kotlin-specific
coroutine, sealed-state, and KDoc guidance remains in its Kotlin reference.
Start a new Codex thread after installing the synchronized update.

## Plugin packaging

`plugin.json` is the portable metadata source. Client manifests and complete skill resources are generated into `me.claude` and `me.codex`; install from those repositories. Source skills use portable frontmatter. Claude routing is stored in `extensions.com.anthropic.claude.skillFrontmatter`, keyed by skill directory, and injected only into generated Claude skills. Codex skill files are copied unchanged.

## Improvement feedback

Plugin findings go to [storytellerF/me issues](https://github.com/storytellerF/me/issues). Skills require checking open and closed issues before reporting, using sanitized or synthetic examples, and honoring the user's authorization before posting. Existing reports are reused; unavailable access leaves an unsubmitted draft.
