---
name: test-report-sharing
description: Use when collecting, previewing, or sharing JUnit XML, Gradle or Maven reports, HTML test output, or end-to-end test artifacts. Assemble a static report site and return either a local preview URL or an ngrok public URL.
context: fork
agent: test-report-operator
---

# Test Report Sharing

## Required Behavior

- Collect reports from standard project locations (build/reports, test output folders).
- Assemble the collected artifacts into a static HTML report site.
- Expose the report site via ngrok if available, otherwise provide a local server URL.
- Return a summary with the public URL and report count.

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
- `REPORT_DIRS`: Colon-separated list of directories to scan for reports
- `NGROK_AUTHTOKEN`: ngrok authentication token (required for public tunnel)
- `NGROK_PORT`: Local port to expose (default: 8080)

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
- Always clean up temporary files and stop background processes on exit.
