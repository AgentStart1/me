# General Coding Practices Plugin

This Codex plugin provides focused skills for project collaboration, README maintenance, verification, rule-file maintenance, root-cause-first debugging, and repository synchronization. The plugin root also contains portable Claude-compatible agent prompts.

## Included guidance

- Project collaboration, privacy, dependency, and generated-file practices.
- README and project-rule maintenance that keeps user documentation concise and action-oriented.
- Flow stabilization, end-to-end test authoring, checks, and verification.
- Structured privacy-safe logging and root-cause-first debugging.
- Repository synchronization and portable Claude agent delegation.

When a skill delegates to a bundled Claude agent, the parent waits for its required final report
before dependent work or its final response. To use this plugin in Codex, generate the local
marketplace from the repository root with `scripts/build-codex-plugin-package.sh --all`.
