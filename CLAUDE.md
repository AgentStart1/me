# me — Claude Code Plugin Collection

This repository publishes Claude Code plugins. Each plugin lives under `plugins/<name>/` with a `.claude-plugin/plugin.json` manifest and one or more skills in `skills/`.

## Plugins

| Plugin | Path | Description |
|--------|------|-------------|
| android-profile | `plugins/android-profile/` | Android SDK/AVD/emulator profile scripts |
| android-appium-device-lock | `plugins/android-appium-device-lock/` | Android Appium, UIAutomator, Espresso, or end-to-end test device lock |
| recyclerview-best-practice | `plugins/recyclerview-best-practice/` | RecyclerView adapter, diff, paging best practices |
| general-coding-practices | `plugins/general-coding-practices/` | General coding, repository delivery, and Kotlin project guidance |
| client-ui-best-practices | `plugins/client-ui-best-practices/` | Client UI threading, Compose state, and handler-driven business-test guidance |
| test-report-sharing | `plugins/test-report-sharing/` | Test result collection, E2E recording, diff report, and ngrok sharing |

## Plugin Structure Convention

```
plugins/<name>/
  .claude-plugin/plugin.json   # Claude Code plugin manifest
  agents/<agent-name>.md       # Plugin-level custom agents
  skills/<skill-name>/SKILL.md # Skill instructions
  README.md                    # Plugin-level documentation
```

## Loaded Skills

@plugins/android-profile/skills/android-profile/SKILL.md
@plugins/android-appium-device-lock/skills/android-appium-device-lock/SKILL.md
@plugins/recyclerview-best-practice/skills/android-recyclerview-best-practice/SKILL.md
@plugins/recyclerview-best-practice/skills/recyclerview-sentinel-viewholder/SKILL.md
@plugins/general-coding-practices/skills/project-collaboration-rules/SKILL.md
@plugins/general-coding-practices/skills/project-readme-maintenance/SKILL.md
@plugins/general-coding-practices/skills/project-checks-and-tests/SKILL.md
@plugins/general-coding-practices/skills/project-rule-file-maintenance/SKILL.md
@plugins/general-coding-practices/skills/project-logging-rules/SKILL.md
@plugins/general-coding-practices/skills/root-cause-before-fallback/SKILL.md
@plugins/general-coding-practices/skills/github-pr-ci/SKILL.md
@plugins/general-coding-practices/skills/repository-sync/SKILL.md
@plugins/general-coding-practices/skills/release-infra/SKILL.md
@plugins/general-coding-practices/skills/kotlin-project-rules/SKILL.md
@plugins/client-ui-best-practices/skills/client-ui-best-practices/SKILL.md
@plugins/test-report-sharing/skills/test-report-sharing/SKILL.md
@AGENTS.md

## Agent prompts

Reusable prompts live at plugin root under `plugins/*/agents/`, alongside each plugin's `skills/` directory. The repository
prompt at `agents/me-agent-config-maintainer.md` maintains these files, their triggers, and manual
installation instructions. Claude Code uses the Markdown files directly.
