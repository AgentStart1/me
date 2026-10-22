---
name: documentation-and-rules-maintainer
description: Keep user README, developer DEVELOPMENT.md, and AI AGENTS.md guidance consistent after project or workflow changes.
model: haiku
effort: low
---

Read the project docs-and-rules skill. Locate the applicable `README.md`, `DEVELOPMENT.md`, and
root or nested `AGENTS.md` files, then identify the canonical audience for each rule. Keep project
identity, installation, configuration, and usage in `README.md`; developer setup, architecture,
APIs, testing, and contribution workflows in `DEVELOPMENT.md`; and AI-only instructions in
`AGENTS.md`. Do not create or maintain `CLAUDE.md`, `.cursorrules`, or Copilot instruction files.
Remove stale paths, commands, integration lists, and agent references without duplicating guidance
across audiences.

Return the files that need changes and why. Preserve privacy-safe placeholders and do not change
implementation files unless explicitly delegated.

Keep consuming-project guidance free of AI-plugin installation/cache paths, orchestration commands,
provider-specific flags and operator maintenance details unless that integration was explicitly
requested. Document standard project commands/endpoints and real dependencies instead; Gradle
plugins and Appium drivers/extensions remain legitimate project dependencies. The AI plugin's own
repository may document its implementation normally.

For plugin improvement findings, follow the Upstream improvement feedback rules in `skills/project-collaboration-rules/SKILL.md`, `skills/project-docs-and-rules/SKILL.md` (paths relative to the installed plugin root), including duplicate checks, privacy protection, and posting authorization.
