# Repository maintenance rules

This repository is the source of truth for the `me` plugin collection and its portable agent prompts.

## Agent and Claude compatibility

- Keep reusable agent prompts at the owning plugin root in `plugins/*/agents/*.md`, alongside that plugin's `skills/` directory.
- Keep Claude agent instructions in Markdown with only Claude-compatible frontmatter: `name`, `description`, `model`, and `effort`.
- Preserve `context: fork` and `agent: <agent-name>` in source skill frontmatter when they route work to a Claude agent. Do not remove those fields merely to satisfy a Codex-only validator.
- Do not claim that installing a plugin automatically installs agents.

## Codex package generation and validation

- Before validating or loading plugins whose source skills contain Claude routing fields, run `scripts/build-codex-plugin-package.sh --all`. It generates packages in `build/codex/plugins/` and the marketplace at `build/codex/.agents/plugins/marketplace.json`.
- Commit the generated `build/codex/` directory. Whenever source plugins or the marketplace template change, regenerate it and include the synchronized build artifacts in the same commit.
- Run `skill-creator/scripts/quick_validate.py` only against generated skill copies, never against Claude-oriented source skills. Validate the corresponding generated plugin manifests as well.
- Validate changed skills and manifests, and confirm regenerating `build/` leaves no diff before handoff. Tell the user when a new Codex thread is needed to load plugin changes.

## Documentation and versioning

- When a skill or agent changes, update its owning `SKILL.md`, `README.md`, and any applicable `CLAUDE.md` references. Custom agent prompts remain at the plugin root.
- Use `MAJOR.MINOR.PATCH-YYYYMMDDHHMMSS` for every plugin version. Keep `.codex-plugin/plugin.json` and `.claude-plugin/plugin.json` versions identical, and do not add environment or tool labels.
- Upgrade a plugin version at most once in the same PR. After that first upgrade, do not change its version or refresh its timestamp for later commits in that PR; the timestamp records when the version was initially updated. Make a further version change only in a new PR.

## Privacy

- Keep prompts privacy-safe and generalized. Never copy raw account conversation content, secrets, or personal identifiers into this repository.
