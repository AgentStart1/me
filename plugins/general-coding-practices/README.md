# General Coding Practices Plugin

This plugin provides project collaboration rules plus focused README and project-guidance maintenance. The plugin root also contains a portable Claude-compatible documentation agent prompt.

## Included guidance

- Project collaboration that follows the existing plan autonomously and asks for user input only when a blocker prevents further progress, plus privacy, dependency, generated-file, and focused commit practices.
- Root-cause-first debugging with structured, privacy-safe logging guidance.
- Focused test, formatter, lint, static-analysis, and build verification.
- README and project-rule maintenance that keeps guidance concise and audience-appropriate.
- Portable Claude documentation-agent delegation.

When a skill delegates to a bundled Claude agent, the parent waits for its required final report
before dependent work or its final response.
