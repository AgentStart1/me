# General Coding Practices Plugin

This plugin provides project collaboration rules plus focused README and project-guidance maintenance. The plugin root also contains a portable Claude-compatible documentation agent prompt.

## Included guidance

- Project collaboration, approval, privacy, dependency, generated-file, and commit practices.
- Root-cause-first debugging with structured, privacy-safe logging guidance.
- Focused test, formatter, lint, static-analysis, and build verification.
- README and project-rule maintenance that keeps guidance concise and audience-appropriate.
- Portable Claude documentation-agent delegation.

When a skill delegates to a bundled Claude agent, the parent waits for its required final report
before dependent work or its final response. Codex-compatible packages are generated, validated,
and proposed to the standalone `me.codex` repository by the source repository's synchronization
workflow after changes merge to `main`. Contributors may generate the packages locally for review
and validation, but the workflow owns commits, pushes, and pull requests for generated changes.
