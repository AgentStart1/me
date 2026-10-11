# Test Report Sharing Plugin

Collect test reports, then share a static report site through ngrok.

## Workflow

```bash
plugins/test-report-sharing/scripts/collect-test-results.sh
plugins/test-report-sharing/scripts/generate-report-site.sh
plugins/test-report-sharing/scripts/start-ngrok.sh
```

`test-report-operator` coordinates the same workflow when Claude agent routing is available.

For an installed plugin, use absolute script paths from its root while staying in
the tested project's directory. Collection discovers HTML roots and nested JUnit XML
up to four directory levels below each search root. Overlapping HTML roots are
deduplicated; same-named XML from different paths are retained separately and linked
from the site. Keep the output outside a report being copied.

`start-ngrok.sh --local-only` serves the site on `127.0.0.1`. The normal launcher
also stays local if ngrok is absent or authentication fails. Credentials may come
from saved configuration or `NGROK_AUTHTOKEN`. Keep the launcher running while using
its URL; Ctrl+C stops only that launcher's server and tunnel.

## Configuration

| Variable | Description | Default |
|---|---|---|
| `REPORT_OUTPUT_DIR` | Output directory for collected reports | `~/.cache/test-reports/<project-hash>` |
| `TEST_RESULT_DIRS` | Colon-separated report directories; `REPORT_DIRS` is an alias | Auto-detect HTML/JUnit locations |
| `NGROK_AUTHTOKEN` | ngrok token override | Saved credentials when unset |
| `NGROK_PORT` | Local port to expose | `8080` |
| `PYTHON_COMMAND` | Working Python 3 executable | `python3`, then `python` |

## Requirements

- **Bash 4.0+** for the scripts.
- **ngrok** for public sharing; otherwise use the local server URL.
- **Python 3** for the local HTTP-server fallback.
- **jq** for collection summaries and GNU-compatible `find`, `sort`, `sed` and core utilities.

## License

This plugin is part of the me plugin collection.

## Plugin packaging

`plugin.json` is the portable metadata source. Client manifests and complete skill resources are generated into `me.claude` and `me.codex`; install from those repositories. Source skills use portable frontmatter. Claude routing is stored in `extensions.com.anthropic.claude.skillFrontmatter`, keyed by skill directory, and injected only into generated Claude skills. Codex skill files are copied unchanged.
