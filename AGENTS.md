# Repository maintenance rules

This repository is the source of truth for the `me` plugin collection and its portable agent prompts.

## Agent and Claude compatibility

- Keep reusable agent prompts at the owning plugin root in `plugins/*/agents/*.md`, alongside that plugin's `skills/` directory.
- Keep Claude agent instructions in Markdown with only Claude-compatible frontmatter: `name`, `description`, `model`, and `effort`.
- Preserve `context: fork` and `agent: <agent-name>` in source skill frontmatter when they route work to a Claude agent. Do not remove those fields merely to satisfy a Codex-only validator.
- Do not claim that installing a plugin automatically installs agents.

## Codex package generation and validation

- Run `scripts/build-codex-plugin-package.sh --all` after source changes to generate packages into the local sibling `../me.codex` checkout for review and validation. The command replaces previously generated content, so inspect the sibling checkout before running it and preserve unrelated work.
- Validate the generated skill copies, plugin manifests, marketplace, and relevant plugin installation behavior locally before handoff. Never run Codex-only validation directly against Claude-oriented source skills.
- Treat `.github/workflows/sync-me-codex.yml` as the only supported path for committing, pushing, and proposing generated changes to the upstream `me.codex` repository. It runs after changes merge to `main` and may also be started manually through GitHub Actions.
- Do not commit generated packages in the local `me.codex` checkout, push synchronization branches, or open `me.codex` pull requests manually.
- Keep generation and validation logic in the source repository so local checks and the workflow remain reproducible.
- Validate source and locally generated changes before handoff. Tell the user when a new Codex thread is needed after the workflow publishes the synchronized plugin changes.

## Documentation and versioning

- When a skill or agent changes, update its owning `SKILL.md`, `README.md`, and any applicable `CLAUDE.md` references. Custom agent prompts remain at the plugin root.
- Use `MAJOR.MINOR.PATCH-YYYYMMDDHHMMSS` for every plugin version. Keep `.codex-plugin/plugin.json` and `.claude-plugin/plugin.json` versions identical, and do not add environment or tool labels.
- Upgrade a plugin version at most once in the same PR. After that first upgrade, do not change its version or refresh its timestamp for later commits in that PR; the timestamp records when the version was initially updated. Make a further version change only in a new PR.

## Privacy

- Keep prompts privacy-safe and generalized. Never copy raw account conversation content, secrets, or personal identifiers into this repository.
