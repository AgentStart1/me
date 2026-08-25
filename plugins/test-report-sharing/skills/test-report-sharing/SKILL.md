---
name: test-report-sharing
description: Collect reports and selectable Git or Difftastic code diffs, then share them via a public ngrok tunnel.
context: fork
agent: test-report-operator
---

# Test Report Sharing

Use this skill when you need to collect reports (unit tests, E2E tests, etc.) and code diffs, then generate a shareable report site exposed via ngrok.

## Required Behavior

- Collect reports from standard project locations (build/reports, test output folders).
- E2E test reports should include video recordings of the test runs.
- Generate an HTML diff report from the current git branch compared to main or a specified base.
- Include a page control for switching between ordinary Git diff and locally rendered Difftastic JSON when `difft` is installed; within Difftastic, support inline and side-by-side layout switching; keep Git diff usable when it is not.
- Switch the header summary with the renderer: Git reports line insertions/deletions, while Difftastic reports files compared, structural model, and display mode.
- Assemble all artifacts into a static HTML site with navigation between reports and diffs.
- Expose the report site via ngrok if available, otherwise provide a local server URL.
- Return a summary with public URL, report count, and diff statistics.

## Quick Start

Use the bundled scripts for manual execution:

```bash
# Collect reports
plugins/test-report-sharing/scripts/collect-test-results.sh

# Generate diff report
plugins/test-report-sharing/scripts/generate-diff-report.sh

# Generate the full report site
plugins/test-report-sharing/scripts/generate-report-site.sh

# Start ngrok tunnel
plugins/test-report-sharing/scripts/start-ngrok.sh
```

Or run the full workflow via the agent:

```bash
# The agent coordinates all steps automatically
# It will return the public URL and summary
```

## Configuration

- `REPORT_OUTPUT_DIR`: Directory for generated reports (default: `~/.cache/test-reports/<project-hash>`)
- `REPORT_DIRS`: Colon-separated list of directories to scan for reports
- `NGROK_AUTHTOKEN`: ngrok authentication token (required for public tunnel)
- `NGROK_PORT`: Local port to expose (default: 8080)
- `GIT_BASE_REF`: Base ref for diff comparison (default: `main`)
- `DIFFTASTIC_COMMAND`: Difftastic executable name or path (default: `difft`)
- `DIFFTASTIC_WIDTH`: Captured Difftastic output width (default: `160`)
- `DIFFTASTIC_SKIP_UNCHANGED`: omit files where Difftastic detects no change (default: `true`)
- `DIFFTASTIC_PARSE_ERROR_LIMIT`: parse errors allowed before line-oriented fallback (default: `100`)

## Supported Input Formats

### Reports
- JUnit XML reports (`*-tests.xml`, `TEST-*.xml`)
- HTML test reports (`*.html` in test output directories)
- E2E test reports with embedded video playback
- Gradle/Maven test output directories (`build/reports/`)

### Diff Reports
- Git diff output converted to HTML with syntax highlighting
- Optional Difftastic JSON output rendered locally with old/new source context in inline and side-by-side layouts, aligned line numbers, and foreground-only emphasis limited to changed structural fragments
- Supports comparison against any git ref (branch, commit, tag)

## Bundled Resources

- `scripts/collect-test-results.sh`: Collects reports from standard locations
- `scripts/generate-diff-report.sh`: Generates HTML diff report
- `scripts/generate-report-site.sh`: Assembles static HTML report site
- `scripts/start-ngrok.sh`: Starts ngrok tunnel for public access
- `templates/diff-report.html`: Placeholder-based Git/Difftastic report template
- `templates/diff-report.css`: Diff report stylesheet
- `templates/report-site.html`: Placeholder-based report index template
- `templates/style.css`: Report index stylesheet

## Failure Handling

- If no reports are found, generate a report indicating no results were collected.
- If ngrok is not installed or configured, fall back to a local HTTP server.
- If git diff fails, generate a report indicating diff generation failed.
- Always clean up temporary files and stop background processes on exit.
