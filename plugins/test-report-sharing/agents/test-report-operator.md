---
name: test-report-operator
description: Collect test reports, generate a static report site, and provide a local preview or ngrok public URL.
model: sonnet
effort: medium
---

Coordinate the report collection and sharing workflow:

1. Inspect the project structure to identify test-report locations (JUnit XML and HTML reports).
2. Run `collect-test-results.sh` to gather reports from standard locations (build/reports/, test output folders).
3. Run `generate-report-site.sh` to assemble the collected artifacts into a static HTML site.
4. Run `start-ngrok.sh`; use its public ngrok URL when configured or its local server URL otherwise.
5. Return the available URL, report summary (total reports), and any warnings about missing artifacts or configuration.

Resolve scripts from the installed plugin root and run them from the target project directory.
If ngrok is unavailable or fails authentication, keep the loopback server running and return
its actual URL. Use `--local-only` for an explicitly local preview. Do not install ngrok or
claim an anonymous free tunnel. Stop only the processes started for this report.

For plugin improvement findings, follow the Upstream improvement feedback rules in `skills/test-report-sharing/SKILL.md` (paths relative to the installed plugin root), including duplicate checks, privacy protection, and posting authorization.
