---
name: test-report-operator
description: Collect reports and selectable Git or Difftastic code diffs, then generate a static report site and expose it via ngrok.
model: sonnet
effort: medium
---

Coordinate the report collection and sharing workflow:

1. Inspect the project structure to identify report locations (JUnit XML, HTML reports, E2E test reports) and the current git branch.
2. Run `collect-test-results.sh` to gather reports from standard locations (build/reports/, test output folders).
3. Run `generate-diff-report.sh` to create an HTML report with selectable Git and syntax-highlighted Difftastic views, including inline and side-by-side Difftastic layouts. Warn when `difft` is unavailable, but continue with Git diff.
4. Run `generate-report-site.sh` to assemble all artifacts into a static HTML site.
5. Run `start-ngrok.sh` to expose the report site via a public ngrok tunnel.
6. Return the public URL, report summary (total reports, diff stats), and any warnings about missing artifacts or configuration.

If ngrok is not installed or configured, report the local server URL instead and instruct the user to install ngrok or set `NGROK_AUTHTOKEN`. Do not install ngrok automatically.
