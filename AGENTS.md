# Agent maintenance rules

This repository is the source of truth for the `me` Codex plugin collection and its portable agent prompts.

- Keep reusable agent prompts at the plugin root in `plugins/*/agents/*.md`, alongside the plugin's `skills/` directory.
- Keep prompts specific to this repository under `agents/`; do not place one-off application behavior in the global collection.
- Preserve Claude-compatible Markdown frontmatter. Put Codex model recommendations in the prompt body and treat them as routing hints when the runtime inherits a model.
- When a skill or agent changes, proactively update the owning `SKILL.md`, the skill-owned `agents/openai.yaml` only when its Codex UI metadata is stale, `README.md`, and applicable `CLAUDE.md` references. The custom agent prompts themselves belong at plugin root.
- Use `scripts/install-agents.sh` for manual installation into global or project-local `.codex/agents` and `.claude/agents` directories. Do not claim that installing a plugin automatically installs agents.
- Validate changed skills and the plugin manifest before handoff, and tell the user when a new Codex thread is needed to load plugin changes.
- Keep prompts privacy-safe and generalized; never copy raw account conversation content, secrets, or personal identifiers into this repository.

The repository-level maintenance prompt is [`agents/me-agent-config-maintainer.md`](agents/me-agent-config-maintainer.md).
