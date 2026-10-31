---
name: test-report-sharing
description: Use when collecting existing test reports into a browsable site, previewing reports, or sharing a report URL. Supports JUnit XML and HTML output from tools such as Gradle and Maven. Do not trigger merely because tests are being run or failures analyzed.
---

# Test Report Sharing

Use existing test outputs for a report request. Running tests, diagnosing failures, or changing test-report generation is a separate task unless the user also requests it.

## Project independence

Consume the project's existing JUnit/XML/HTML outputs without making its build or tests invoke this AI plugin's collector, viewer or tunnel scripts. Keep helper paths, credentials, sharing configuration and server state outside the project, and use the report cache by default. Standard test-report/coverage Gradle plugins remain normal project dependencies. Preserve user-requested output destinations; adding project-owned report generation or persistent sharing integration must be within the requested task.

## Required Behavior

- Accept `--project-dir DIR` on collection, site assembly and serving, defaulting to the calling directory. Resolve report searches and relative custom report directories from that project; use it for cache identity.
- Exclude registered submodule directories from searches and copied report trees, including explicitly supplied roots.
- Collect reports from standard project locations (build/reports, test output folders).
- Assemble the collected artifacts into a static HTML report site.
- For a local preview or an unspecified audience, serve with `--local-only`; use ngrok when public sharing is requested. Saved credentials alone do not select public sharing.
- Return the actual public or local URL and report count; no collected reports does not imply passing tests.
- Resolve scripts from the installed plugin root and run them by absolute path
  from the target project; relative Quick Start paths are for the source checkout.

## Runtime

All control logic runs in Python 3.10+ using its standard library. Existing `.sh` commands are thin launchers; each also has a same-named `.py` entrypoint for direct native execution. Use the same `--project-dir` throughout the workflow. Resolve explicit relative output paths from the original calling directory without changing the caller working directory. GNU text utilities and jq are not runtime requirements.

## Quick Start

Use the bundled scripts for manual execution:

```bash
# Collect reports
plugins/test-report-sharing/scripts/collect-test-results.sh

# Generate the full report site
plugins/test-report-sharing/scripts/generate-report-site.sh

# Start a local preview
plugins/test-report-sharing/scripts/start-ngrok.sh --local-only
```

## Configuration

- `--project-dir DIR`: Project directory for every command (default: current directory)

- `REPORT_OUTPUT_DIR`: Directory for generated reports (default: `~/.cache/test-reports/<project-hash>`)
- `TEST_RESULT_DIRS`: Legacy colon-separated directories to scan; `REPORT_DIRS` remains an alias. Prefer repeated `--test-dir DIR` for Windows drive paths
- `NGROK_AUTHTOKEN`: token override; authenticated saved configuration is also supported
- `NGROK_PORT`: Local port to expose (default: 8080)
- `PYTHON_COMMAND`: explicit working Python 3.10+ executable for every command; otherwise try `python3`, then `python`
- `start-ngrok.sh --local-only`: loopback preview without attempting a public tunnel

## Supported Input Formats

### Reports
- JUnit XML reports (`*-tests.xml`, `TEST-*.xml`)
- HTML test reports (`*.html` in test output directories)
- Gradle/Maven test output directories (`build/reports/`)

## Bundled Resources

- `scripts/collect-test-results.sh`: Collects reports from standard locations
- `scripts/generate-report-site.sh`: Assembles static HTML report site
- `scripts/start-ngrok.sh`: Serves a local preview or starts a public ngrok tunnel.
- `templates/report-site.html`: Placeholder-based report index template
- `templates/style.css`: Report index stylesheet

## Failure Handling

- If no reports are found, generate a report indicating no results were collected.
- If ngrok is not installed or configured, fall back to a local HTTP server.
- Public tunnels need working credentials from environment or saved configuration;
  do not claim anonymous free-tier access. Keep the loopback launcher alive while
  its URL is in use, then stop only its own children. Preserve existing report services.
- Collection supports nested JUnit XML within the bounded scan, deduplicates
  overlapping report roots and gives same-named XML from different paths distinct
  output names. Failed copies must not count as collected results. Keep output
  outside a report being copied to avoid recursive self-collection.

## Upstream improvement feedback

- Report actionable plugin bugs or reusable improvements to [storytellerF/me](https://github.com/storytellerF/me/issues), identifying the plugin and skill. Exclude project-only problems without evidence of a plugin defect. Finish the primary task before non-blocking feedback work.
- Before searching or posting, reduce evidence to a minimal privacy-safe summary or synthetic reproduction. Never disclose raw conversations, private code, logs, screenshots, credentials, personal/account data, or private paths/URLs. Keep findings local if safe disclosure is impossible.
- Search open and closed issues and read likely matches and resolutions. Reuse matching reports; a distinct regression or uncovered case may need a linked new issue. Posting a new issue or a materially useful comment requires existing user authorization; this rule grants none. Without authorization, prepare an unsubmitted draft.
- Include the plugin/skill version, observed and expected behavior, reproduction or proposal, and duplicate-search results; prefix new issue titles with the plugin name. On access or submission failure, retain the draft and explain the blocker. After an uncertain submission, check whether it succeeded before retrying. Return the report link or clearly label the draft as unsubmitted.


Each collection publishes a complete replacement snapshot, including its site.
Repeating collection does not duplicate reports in the current view; removed
source reports disappear from the next snapshot. Failed collection leaves the
previous version available. Use the launcher URL for the latest snapshot; open
pages keep their original assets. Older generations are retained, so remove the
dedicated report cache only after its servers and readers have finished.

Materialize linked assets when publishing a snapshot. Reject directory cycles and
retain the previous publication on copy failure; do not keep live source links.
