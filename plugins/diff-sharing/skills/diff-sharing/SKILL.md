---
name: diff-sharing
description: Use when the user wants a browsable HTML code-diff report or a URL to preview or share branch, pull request, commit, or working-tree changes. Do not trigger for ordinary Git inspection, code review, or patch editing without a report, preview, or sharing request.
---

# Diff Sharing

For test-report previews or sharing, use `test-report-sharing` when available. This skill produces a diff site; ordinary code inspection or review does not require starting a report server.

## Project independence

Render and serve differences through externally resolved helpers and the plugin's report cache. Do not modify project builds, CI, dependencies or documentation, vendor helpers, or add AI-plugin commands merely to share a diff. Keep tunnel credentials and process state outside the project. Project-owned documentation/report artifacts or persistent integration may be added when explicitly requested; normal Git/build-plugin dependencies are unaffected.

## Required Behavior

- Generate an HTML diff report for the current branch against `main`, or a user-specified base ref.
- Prefer Difftastic (`difft`) as the initial renderer when it is available. Offer Git diff as an alternate renderer.
- When Difftastic is unavailable, make the Git renderer the only usable default and clearly report the missing executable; do not install it automatically.
- Resolve Git operations and cache identity against the detected repository root, regardless of the invocation subdirectory. Use that root for the default cache and all comparison queries. Keep committed comparisons isolated from working-tree content; a deleted side must remain empty.
- Exclude submodule changes from statistics, Git patches and Difftastic output.
- Preserve Difftastic's inline and side-by-side layout controls, old/new source context, and changed structural-fragment emphasis.
- Assemble the generated diff into the static report site. For a local preview or an unspecified audience, serve with `--local-only`; use ngrok when public sharing is requested. Saved credentials alone do not select public sharing.
- Return the public or local URL, compared refs, renderer used by default, and diff statistics.
- Resolve scripts from the installed plugin root and invoke them by absolute path
  from the target project. The relative Quick Start below is for this source checkout.

## Runtime

All control logic runs in Python 3.10+ using its standard library. Existing `.sh` commands are thin launchers; each also has a same-named `.py` entrypoint for direct native execution. Resolve explicit relative output paths from the original calling directory without changing the caller working directory. GNU text utilities and jq are not runtime requirements.

## Quick Start

```bash
plugins/diff-sharing/scripts/generate-diff-report.sh
plugins/diff-sharing/scripts/generate-diff-site.sh
plugins/diff-sharing/scripts/start-ngrok.sh --local-only
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

- Report actionable plugin bugs or reusable improvements to [storytellerF/me](https://github.com/storytellerF/me/issues), identifying the plugin and skill. Exclude project-only problems without evidence of a plugin defect. Finish the primary task before non-blocking feedback work.
- Before searching or posting, reduce evidence to a minimal privacy-safe summary or synthetic reproduction. Never disclose raw conversations, private code, logs, screenshots, credentials, personal/account data, or private paths/URLs. Keep findings local if safe disclosure is impossible.
- Search open and closed issues and read likely matches and resolutions. Reuse matching reports; a distinct regression or uncovered case may need a linked new issue. Posting a new issue or a materially useful comment requires existing user authorization; this rule grants none. Without authorization, prepare an unsubmitted draft.
- Include the plugin/skill version, observed and expected behavior, reproduction or proposal, and duplicate-search results; prefix new issue titles with the plugin name. On access or submission failure, retain the draft and explain the blocker. After an uncertain submission, check whether it succeeded before retrying. Return the report link or clearly label the draft as unsubmitted.


Each successful generation publishes a complete snapshot. Failed builds leave the
previous report available, and open pages keep their original assets. Use the
launcher URL to open the latest snapshot. Older generations are retained; remove
the dedicated report cache only after its servers and readers have finished.
Invalid comparison refs fail explicitly without substituting another history.
When Difftastic exists but rendering fails, the page selects the usable Git diff.
