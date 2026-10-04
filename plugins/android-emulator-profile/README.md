# Android Emulator Profile Plugin

This plugin provides profile-driven Android Virtual Device creation and emulator startup for local and Docker-friendly environments.

## Included tooling

- Install Android SDK command-line tools and accept licenses.
- Create AVDs from mobile, tablet, desktop, TV, and watch profiles.
- Start emulators with architecture-aware defaults.
- Run a fake-command smoke test without starting a real emulator.

## Plugin packaging

`plugin.json` is the portable metadata source. Client manifests and complete skill resources are generated into `me.claude` and `me.codex`; install from those repositories. Source skills use portable frontmatter. Claude routing is stored in `extensions.com.anthropic.claude.skillFrontmatter`, keyed by skill directory, and injected only into generated Claude skills. Codex skill files are copied unchanged.
