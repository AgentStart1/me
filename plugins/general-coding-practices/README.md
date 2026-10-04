# General Coding Practices Plugin

This plugin provides project collaboration rules plus focused README and project-guidance maintenance. The plugin root also contains a portable Claude-compatible documentation agent prompt.

## Included guidance

- Project collaboration that follows the existing plan autonomously and asks for user input only when a blocker prevents further progress, plus privacy, dependency, generated-file, and focused commit practices.
- Root-cause-first debugging with structured, privacy-safe logging guidance.
- Focused test, formatter, lint, static-analysis, and build verification.
- Audience-specific documentation maintenance: user guidance in `README.md`, developer guidance in `DEVELOPMENT.md`, and AI guidance in `AGENTS.md`.
- Portable Claude documentation-agent delegation.

When a skill delegates to a bundled Claude agent, the parent waits for its required final report
before dependent work or its final response.

## Plugin packaging

`plugin.json` is the portable metadata source. Client manifests and complete skill resources are generated into `me.claude` and `me.codex`; install from those repositories. Source skills use portable frontmatter. Claude routing is stored in `extensions.com.anthropic.claude.skillFrontmatter`, keyed by skill directory, and injected only into generated Claude skills. Codex skill files are copied unchanged.
