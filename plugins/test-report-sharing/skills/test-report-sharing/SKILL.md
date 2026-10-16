---
name: test-report-sharing
description: Use when collecting, previewing, or sharing test reports such as JUnit XML, Gradle or Maven reports, and HTML test output. Assemble a static report site and return either a local preview URL or an ngrok public URL.
---

# Test Report Sharing

## Required Behavior

- Collect reports from standard project locations (build/reports, test output folders).
- Assemble the collected artifacts into a static HTML report site.
- Expose the report site via ngrok if available, otherwise provide a local server URL.
- Return a summary with the public URL and report count.
- Resolve scripts from the installed plugin root and run them by absolute path
  from the target project; relative Quick Start paths are for the source checkout.

## Quick Start

Use the bundled scripts for manual execution:

```bash
# Collect reports
plugins/test-report-sharing/scripts/collect-test-results.sh

# Generate the full report site
plugins/test-report-sharing/scripts/generate-report-site.sh

# Start ngrok tunnel
plugins/test-report-sharing/scripts/start-ngrok.sh
```

## Configuration

- `REPORT_OUTPUT_DIR`: Directory for generated reports (default: `~/.cache/test-reports/<project-hash>`)
- `TEST_RESULT_DIRS`: Colon-separated directories to scan; `REPORT_DIRS` remains an alias
- `NGROK_AUTHTOKEN`: token override; authenticated saved configuration is also supported
- `NGROK_PORT`: Local port to expose (default: 8080)
- `PYTHON_COMMAND`: explicit working Python 3 executable; otherwise try `python3`, then `python`
- `start-ngrok.sh --local-only`: loopback preview without attempting a public tunnel

## Supported Input Formats

### Reports
- JUnit XML reports (`*-tests.xml`, `TEST-*.xml`)
- HTML test reports (`*.html` in test output directories)
- Gradle/Maven test output directories (`build/reports/`)

## Bundled Resources

- `scripts/collect-test-results.sh`: Collects reports from standard locations
- `scripts/generate-report-site.sh`: Assembles static HTML report site
- `scripts/start-ngrok.sh`: Starts ngrok tunnel for public access
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

- When using this plugin reveals an actionable bug, missing guidance, or reusable improvement, report it to [storytellerF/me](https://github.com/storytellerF/me/issues). Identify the owning plugin and skill; do not report project-specific problems without evidence that the plugin needs a change. Finish the user's primary task before non-blocking feedback work.
- Before any search or submission, reduce the finding to a privacy-safe summary. Never send raw conversations, private source code, logs, screenshots, credentials, personal identifiers, account data, or private paths/URLs. Use synthetic examples and the minimum non-sensitive environment details needed to explain the problem. If safe disclosure is impossible, keep the finding local.
- Search both open and closed upstream issues using the plugin name and sanitized symptom keywords. Read likely matches and their resolution; do not rely only on title matches. Reuse a matching issue link instead of opening a duplicate. Add a comment only when it supplies materially new, safe evidence and posting is authorized. A closed issue warrants a new report only for a distinct regression or uncovered case, with a link explaining the difference.
- Submit a new issue when no duplicate exists and the user has authorized upstream reporting in the current session or standing instructions. This rule alone does not authorize external posting. Honor existing authorization without asking again; otherwise prepare a sanitized draft for approval.
- Include the plugin/skill and version, observed and expected behavior, a minimal synthetic reproduction or concrete improvement proposal, and relevant duplicate-search results. Use a concise title prefixed with the plugin name.
- If search, authentication, or submission fails, retain the sanitized draft and explain the blocker; do not post without completing duplicate checks. After an uncertain submission result, check for the created issue before retrying. Return the existing or created issue URL, or clearly mark the report as an unsubmitted draft.
