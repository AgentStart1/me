---
name: diff-sharing
description: Use when generating, previewing, or sharing code differences for branches, pull requests, commits, or uncommitted working-tree changes. Render Git or Difftastic output as a static site and return either a local preview URL or an ngrok public URL.
---

# Diff Sharing

Use `test-report-sharing` instead when the task is to collect, preview, or share test reports.

## Project independence

Render and serve differences through externally resolved helpers and the plugin's report cache. Do not modify project builds, CI, dependencies or documentation, vendor helpers, or add AI-plugin commands merely to share a diff. Keep tunnel credentials and process state outside the project. Project-owned documentation/report artifacts or persistent integration may be added when explicitly requested; normal Git/build-plugin dependencies are unaffected.

## Required Behavior

- Generate an HTML diff report for the current branch against `main`, or a user-specified base ref.
- Prefer Difftastic (`difft`) as the initial renderer when it is available. Offer Git diff as an alternate renderer.
- When Difftastic is unavailable, make the Git renderer the only usable default and clearly report the missing executable; do not install it automatically.
- Resolve Git operations and cache identity against the detected repository root, regardless of the invocation subdirectory. Use that root for the default cache and all comparison queries. Keep committed comparisons isolated from working-tree content; a deleted side must remain empty.
- Exclude submodule changes from statistics, Git patches and Difftastic output.
- Preserve Difftastic's inline and side-by-side layout controls, old/new source context, and changed structural-fragment emphasis.
- Assemble the generated diff into the static report site, then expose it through ngrok when configured; otherwise return the local server URL.
- Return the public or local URL, compared refs, renderer used by default, and diff statistics.
- Resolve scripts from the installed plugin root and invoke them by absolute path
  from the target project. The relative Quick Start below is for this source checkout.

## Runtime

All control logic runs in Python 3.10+ using its standard library. Existing `.sh` commands are thin launchers; each also has a same-named `.py` entrypoint for direct native execution. All Git operations explicitly use the repository root; cache identity also uses that root. Resolve explicit relative output paths from the original calling directory without changing the caller working directory. GNU text utilities and jq are not runtime requirements.

## Quick Start

```bash
plugins/diff-sharing/scripts/generate-diff-report.sh
plugins/diff-sharing/scripts/generate-diff-site.sh
plugins/diff-sharing/scripts/start-ngrok.sh
```

## Configuration

- `REPORT_OUTPUT_DIR`: Directory for generated artifacts (default: `~/.cache/diff-reports/<project-hash>`)
- `NGROK_AUTHTOKEN`: token override; authenticated saved configuration is also supported
- `NGROK_PORT`: Local port to expose (default: `8080`)
- `PYTHON_COMMAND`: Python 3.10+ executable used by all shell launchers (default: first working candidate among `python3` and `python`)
- `start-ngrok.sh --local-only`: keep the report on loopback without attempting a tunnel
- `GIT_BASE_REF`: Base ref for diff comparison (default: `main`)
- `GIT_COMPARE_REF`: Compare ref when `GIT_INCLUDE_UNCOMMITTED=false` (default: `HEAD`)
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
- Public tunnels need working ngrok credentials, supplied by environment or saved
  configuration. Do not claim anonymous free-tier access. Serve locally on
  `127.0.0.1` until the caller stops the launcher; stop only this launcher's children.
- If `python3` is older than Python 3.10 or cannot run, use a `python` command that passes the version check; honor `PYTHON_COMMAND` when the interpreter needs an explicit path.

## Upstream improvement feedback

- When using this plugin reveals an actionable bug, missing guidance, or reusable improvement, report it to [storytellerF/me](https://github.com/storytellerF/me/issues). Identify the owning plugin and skill; do not report project-specific problems without evidence that the plugin needs a change. Finish the user's primary task before non-blocking feedback work.
- Before any search or submission, reduce the finding to a privacy-safe summary. Never send raw conversations, private source code, logs, screenshots, credentials, personal identifiers, account data, or private paths/URLs. Use synthetic examples and the minimum non-sensitive environment details needed to explain the problem. If safe disclosure is impossible, keep the finding local.
- Search both open and closed upstream issues using the plugin name and sanitized symptom keywords. Read likely matches and their resolution; do not rely only on title matches. Reuse a matching issue link instead of opening a duplicate. Add a comment only when it supplies materially new, safe evidence and posting is authorized. A closed issue warrants a new report only for a distinct regression or uncovered case, with a link explaining the difference.
- Submit a new issue when no duplicate exists and the user has authorized upstream reporting in the current session or standing instructions. This rule alone does not authorize external posting. Honor existing authorization without asking again; otherwise prepare a sanitized draft for approval.
- Include the plugin/skill and version, observed and expected behavior, a minimal synthetic reproduction or concrete improvement proposal, and relevant duplicate-search results. Use a concise title prefixed with the plugin name.
- If search, authentication, or submission fails, retain the sanitized draft and explain the blocker; do not post without completing duplicate checks. After an uncertain submission result, check for the created issue before retrying. Return the existing or created issue URL, or clearly mark the report as an unsubmitted draft.


Each successful generation publishes a complete snapshot. Failed builds leave the
previous report available, and open pages keep their original assets. Use the
launcher URL to open the latest snapshot. Older generations are retained; remove
the dedicated report cache only after its servers and readers have finished.
Invalid comparison refs fail explicitly without substituting another history.
When Difftastic exists but rendering fails, the page selects the usable Git diff.
