# me — Codex Plugin Collection

This repository publishes Codex plugins. Each plugin lives under `plugins/<name>/` with a `.codex-plugin/plugin.json` manifest and one or more skills in `skills/`.

## Plugins

| Plugin | Path | Description |
|--------|------|-------------|
| android-profile | `plugins/android-profile/` | Android SDK/AVD/emulator profile scripts |
| recyclerview-best-practice | `plugins/recyclerview-best-practice/` | RecyclerView adapter, diff, paging best practices |
| general-coding-practices | `plugins/general-coding-practices/` | General coding and Kotlin project guidance |

## Plugin Structure Convention

```
plugins/<name>/
  .codex-plugin/plugin.json    # Plugin manifest (name, version, description, interface)
  skills/<skill-name>/SKILL.md # Skill instructions
  README.md                    # Plugin-level documentation
```

When adding a new plugin, also register it in `.agents/plugins/marketplace.json`.

## Loaded Skills

@plugins/android-profile/skills/android-profile/SKILL.md
@plugins/recyclerview-best-practice/skills/android-recyclerview-best-practice/SKILL.md
@plugins/recyclerview-best-practice/skills/recyclerview-sentinel-viewholder/SKILL.md
@plugins/general-coding-practices/skills/project-collaboration-rules/SKILL.md
@plugins/general-coding-practices/skills/project-checks-and-tests/SKILL.md
@plugins/general-coding-practices/skills/project-rule-file-maintenance/SKILL.md
@plugins/general-coding-practices/skills/root-cause-before-fallback/SKILL.md
@plugins/general-coding-practices/skills/kotlin-project-rules/SKILL.md
