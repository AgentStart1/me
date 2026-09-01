# Test Report Sharing Plugin

Collect test reports, then share a static report site through ngrok.

## Workflow

```bash
plugins/test-report-sharing/scripts/collect-test-results.sh
plugins/test-report-sharing/scripts/generate-report-site.sh
plugins/test-report-sharing/scripts/start-ngrok.sh
```

`test-report-operator` coordinates the same workflow when Claude agent routing is available.

## Configuration

| Variable | Description | Default |
|---|---|---|
| `REPORT_OUTPUT_DIR` | Output directory for collected reports | `~/.cache/test-reports/<project-hash>` |
| `REPORT_DIRS` | Colon-separated report directories | Auto-detect (`build/reports/`) |
| `NGROK_AUTHTOKEN` | ngrok authentication token | Required for a public tunnel |
| `NGROK_PORT` | Local port to expose | `8080` |

## Requirements

- **Bash 4.0+** for the scripts.
- **ngrok** for public sharing; otherwise use the local server URL.
- **Python 3** for the local HTTP-server fallback.

## License

This plugin is part of the me plugin collection.
