# Repository maintenance rules

This repository is the source of truth for the `me` plugin collection and its portable agent prompts.

## Agent and Claude compatibility

- Keep reusable agent prompts at the owning plugin root in `plugins/*/agents/*.md`, alongside that plugin's `skills/` directory.
- Keep Claude agent instructions in Markdown with only Claude-compatible frontmatter: `name`, `description`, `model`, and `effort`.
- Preserve `context: fork` and `agent: <agent-name>` in source skill frontmatter when they route work to a Claude agent. Do not remove those fields merely to satisfy a Codex-only validator.
- Do not claim that installing a plugin automatically installs agents.

## Codex package generation and validation

- Treat `.github/workflows/sync-me-codex.yml` as the only supported path for generating, validating, committing, and proposing changes to `me.codex`. It runs after changes merge to `main` and may also be started manually through GitHub Actions.
- Do not generate into a local sibling `../me.codex` checkout, commit generated packages there, push synchronization branches, or open `me.codex` pull requests manually.
- Keep generation and validation logic in the source repository so the workflow remains reproducible. `scripts/build-codex-plugin-package.sh` and `scripts/validate-generated-codex-skills.py` are workflow implementation details, not a contributor handoff procedure.
- Never run Codex-only validation directly against Claude-oriented source skills. The workflow validates the generated skill copies, plugin manifests, marketplace, and plugin installation behavior.
- Validate source changes before handoff and rely on the synchronization workflow for generated-package validation. Tell the user when a new Codex thread is needed after the synchronized plugin changes are published.

## Documentation and versioning

- When a skill or agent changes, update its owning `SKILL.md`, `README.md`, and any applicable `CLAUDE.md` references. Custom agent prompts remain at the plugin root.
- Use `MAJOR.MINOR.PATCH-YYYYMMDDHHMMSS` for every plugin version. Keep `.codex-plugin/plugin.json` and `.claude-plugin/plugin.json` versions identical, and do not add environment or tool labels.
- Upgrade a plugin version at most once in the same PR. After that first upgrade, do not change its version or refresh its timestamp for later commits in that PR; the timestamp records when the version was initially updated. Make a further version change only in a new PR.

## Privacy

- Keep prompts privacy-safe and generalized. Never copy raw account conversation content, secrets, or personal identifiers into this repository.
