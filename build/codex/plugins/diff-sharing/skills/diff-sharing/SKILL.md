---
name: diff-sharing
description: Render and share code diffs through a static site and ngrok, using Difftastic by default when it is available.
---

# Diff Sharing

Use this skill to compare the current Git branch with a base ref and share the resulting diff. Use `test-report-sharing` when the task is to collect test results or E2E recordings.

## Required Behavior

- Generate an HTML diff report for the current branch against `main`, or a user-specified base ref.
- Prefer Difftastic (`difft`) as the initial renderer when it is available. Offer Git diff as an alternate renderer.
- When Difftastic is unavailable, make the Git renderer the only usable default and clearly report the missing executable; do not install it automatically.
- Preserve Difftastic's inline and side-by-side layout controls, old/new source context, and changed structural-fragment emphasis.
- Assemble the generated diff into the static report site, then expose it through ngrok when configured; otherwise return the local server URL.
- Return the public or local URL, compared refs, renderer used by default, and diff statistics.

## Quick Start

```bash
plugins/diff-sharing/scripts/generate-diff-report.sh
plugins/diff-sharing/scripts/generate-diff-site.sh
plugins/diff-sharing/scripts/start-ngrok.sh
```

## Configuration

- `REPORT_OUTPUT_DIR`: Directory for generated artifacts (default: `~/.cache/diff-reports/<project-hash>`)
- `NGROK_AUTHTOKEN`: ngrok authentication token (required for public tunnel)
- `NGROK_PORT`: Local port to expose (default: `8080`)
- `GIT_BASE_REF`: Base ref for diff comparison (default: `main`)
- `GIT_COMPARE_REF`: Compare ref (default: `HEAD`)
- `GIT_INCLUDE_UNCOMMITTED`: Include uncommitted changes (default: `true`)
- `DIFFTASTIC_COMMAND`: Difftastic executable name or path (default: `difft`)
- `DIFFTASTIC_WIDTH`: Captured Difftastic output width (default: `160`)
- `DIFFTASTIC_SKIP_UNCHANGED`: Omit unchanged files (default: `true`)
- `DIFFTASTIC_PARSE_ERROR_LIMIT`: Parse errors allowed before line-oriented fallback (default: `100`)

## Bundled Resources

- `scripts/generate-diff-report.sh`: Generates the Git and Difftastic HTML report.
- `scripts/generate-diff-site.sh`: Assembles the static site containing the diff.
- `scripts/start-ngrok.sh`: Exposes the generated site through ngrok or a local server.
- `templates/diff-report.html` and `templates/diff-report.css`: Diff page template and stylesheet.

## Failure Handling

- If Git or the requested base ref is unavailable, report the failure instead of publishing a misleading comparison.
- If Difftastic is unavailable or cannot produce a structural diff, keep the Git diff usable and state why it became the default.
- If ngrok is unavailable or unconfigured, fall back to a local HTTP server URL.
