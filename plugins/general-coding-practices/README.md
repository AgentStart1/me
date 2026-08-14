# General Coding Practices Plugin

This Codex plugin provides focused skills for project collaboration, README maintenance, verification, rule-file maintenance, root-cause-first debugging, repository delivery, and Kotlin project guidance. The plugin root also contains portable Claude-compatible agent prompts.

## Contents

- `.codex-plugin/plugin.json` declares the plugin.
- `.claude-plugin/plugin.json` declares the Claude Code plugin.
- `skills/project-collaboration-rules/SKILL.md` contains collaboration, privacy, duplication, and dependency guidance.
- `skills/project-readme-maintenance/SKILL.md` contains guidance for keeping README files focused on project information and usage.
- `skills/project-checks-and-tests/SKILL.md` contains flow-stabilization, end-to-end test, formatter, static-check, and test-coverage guidance.
- `skills/project-rule-file-maintenance/SKILL.md` contains guidance for keeping `AGENTS.md`, `CLAUDE.md`, and similar project instruction files current.
- `skills/project-logging-rules/SKILL.md` contains guidance for adding necessary, structured, and privacy-safe diagnostic logs.
- `skills/root-cause-before-fallback/SKILL.md` contains root-cause-first debugging guidance.
- `skills/github-pr-ci/SKILL.md` handles GitHub pull requests, code reviews, and CI workflow issues.
- `skills/repository-sync/SKILL.md` synchronizes branches, upstream changes, and submodules.
- `skills/release-infra/SKILL.md` handles release packaging, signing, Docker, proxy, and deployment configuration.
- `skills/kotlin-project-rules/SKILL.md` contains Kotlin coroutine and threading guidance.

Agent prompts are stored in the plugin-root `agents/` directory alongside `skills/`. Their Markdown
frontmatter configures Claude with `model` and `effort`; adjacent `codex-routing.toml` metadata is
promoted by the installer to top-level `model` and `model_reasoning_effort` in Codex TOML files.
When a skill delegates to one of these agents, the parent must wait for its required final report
before dependent work or its final response.

## Local Marketplace Entry

This repository includes `.agents/plugins/marketplace.json` with the local plugin entry:

```json
{
  "name": "general-coding-practices",
  "source": {
    "source": "local",
    "path": "./plugins/general-coding-practices"
  },
  "policy": {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL"
  },
  "category": "Developer Tools"
}
```
