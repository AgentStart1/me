# Repository maintenance rules

This repository is the source of truth for the `me` plugin collection and its portable agent prompts.

## Agent and Claude compatibility

- Keep reusable agent prompts at the owning plugin root in `plugins/*/agents/*.md`, alongside that plugin's `skills/` directory.
- Keep Claude agent instructions in Markdown with only Claude-compatible frontmatter: `name`, `description`, `model`, and `effort`.
- Preserve `context: fork` and `agent: <agent-name>` in source skill frontmatter when they route work to a Claude agent. Do not remove those fields merely to satisfy a Codex-only validator.
- Do not claim that installing a plugin automatically installs agents.

## Codex package generation and validation

- Run `scripts/build-codex-plugin-package.sh --all` after source changes. It writes generated packages and the marketplace directly to the sibling repository `../me.codex`, replacing previously generated content even when that target has uncommitted changes.
- Validate the generated copies in `../me.codex`, review and commit the resulting diff there, then open the upstream PR from `me.codex`.
- Run `skill-creator/scripts/quick_validate.py` only against generated skill copies, never against Claude-oriented source skills. Validate the corresponding generated plugin manifests as well.
- Validate changed skills and manifests before handoff. Tell the user when a new Codex thread is needed to load plugin changes.

## Documentation and versioning

- When a skill or agent changes, update its owning `SKILL.md`, `README.md`, and any applicable `CLAUDE.md` references. Custom agent prompts remain at the plugin root.
- Use `MAJOR.MINOR.PATCH-YYYYMMDDHHMMSS` for every plugin version. Keep `.codex-plugin/plugin.json` and `.claude-plugin/plugin.json` versions identical, and do not add environment or tool labels.
- Upgrade a plugin version at most once in the same PR. After that first upgrade, do not change its version or refresh its timestamp for later commits in that PR; the timestamp records when the version was initially updated. Make a further version change only in a new PR.

## Privacy

- Keep prompts privacy-safe and generalized. Never copy raw account conversation content, secrets, or personal identifiers into this repository.
