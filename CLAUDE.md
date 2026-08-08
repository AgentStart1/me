# me — Codex Plugin Collection

This repository publishes Codex plugins. Each plugin lives under `plugins/<name>/` with a `.codex-plugin/plugin.json` manifest and one or more skills in `skills/`.

## Plugins

| Plugin | Path | Description |
|--------|------|-------------|
| android-profile | `plugins/android-profile/` | Android SDK/AVD/emulator profile scripts |
| recyclerview-best-practice | `plugins/recyclerview-best-practice/` | RecyclerView adapter, diff, paging best practices |
| general-coding-practices | `plugins/general-coding-practices/` | General coding, repository delivery, and Kotlin project guidance |

## Plugin Structure Convention

```
plugins/<name>/
  .codex-plugin/plugin.json    # Plugin manifest (name, version, description, interface)
  .claude-plugin/plugin.json   # Claude Code plugin manifest
  agents/<agent-name>.md       # Plugin-level custom agents
  skills/<skill-name>/SKILL.md # Skill instructions
  README.md                    # Plugin-level documentation
```

When adding a new plugin, also register it in `.agents/plugins/marketplace.json`.

## Loaded Skills

@plugins/android-profile/skills/android-profile/SKILL.md
@plugins/recyclerview-best-practice/skills/android-recyclerview-best-practice/SKILL.md
@plugins/recyclerview-best-practice/skills/recyclerview-sentinel-viewholder/SKILL.md
@plugins/general-coding-practices/skills/project-collaboration-rules/SKILL.md
@plugins/general-coding-practices/skills/project-readme-maintenance/SKILL.md
@plugins/general-coding-practices/skills/project-checks-and-tests/SKILL.md
@plugins/general-coding-practices/skills/project-rule-file-maintenance/SKILL.md
@plugins/general-coding-practices/skills/project-logging-rules/SKILL.md
@plugins/general-coding-practices/skills/root-cause-before-fallback/SKILL.md
@plugins/general-coding-practices/skills/repository-delivery/SKILL.md
@plugins/general-coding-practices/skills/kotlin-project-rules/SKILL.md
@AGENTS.md

## Agent prompts

Reusable prompts live at plugin root under `plugins/*/agents/`, alongside each plugin's `skills/` directory. The repository
prompt at `agents/me-agent-config-maintainer.md` maintains these files, their triggers, and manual
installation instructions. Claude Code uses the Markdown files; adjacent `codex-routing.toml` files
provide Codex model metadata, which the installer combines into top-level `model` and
`model_reasoning_effort` fields because Codex plugin installation does not install custom agents automatically.
