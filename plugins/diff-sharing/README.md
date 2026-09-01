# Diff Sharing Plugin

Generate a Difftastic-first Git diff site and share it through ngrok. Git remains available as a fallback renderer when `difft` is unavailable.

## Workflow

```bash
plugins/diff-sharing/scripts/generate-diff-report.sh
plugins/diff-sharing/scripts/generate-diff-site.sh
plugins/diff-sharing/scripts/start-ngrok.sh
```

When `difft` is on `PATH`, the generated page opens with Difftastic selected. Otherwise it defaults to Git diff and marks Difftastic unavailable.

## Configuration

| Variable | Description | Default |
|---|---|---|
| `REPORT_OUTPUT_DIR` | Output directory for generated artifacts | `~/.cache/diff-reports/<project-hash>` |
| `NGROK_AUTHTOKEN` | ngrok authentication token | Required for a public tunnel |
| `NGROK_PORT` | Local port to expose | `8080` |
| `GIT_BASE_REF` | Base Git ref | `main` |
| `GIT_COMPARE_REF` | Compare Git ref | `HEAD` |
| `GIT_INCLUDE_UNCOMMITTED` | Include uncommitted changes | `true` |
| `DIFFTASTIC_COMMAND` | Difftastic executable name or path | `difft` |
| `DIFFTASTIC_WIDTH` | Captured Difftastic output width | `160` |
| `DIFFTASTIC_SKIP_UNCHANGED` | Omit unchanged files | `true` |
| `DIFFTASTIC_PARSE_ERROR_LIMIT` | Parse errors before text fallback | `100` |

## Requirements

- **Bash 4.0+** for the scripts.
- **Git** for code-diff sharing.
- **Difftastic (`difft`)** for the preferred structural renderer.
- **ngrok** for public sharing; otherwise use the local server URL.
- **Python 3** for the local HTTP-server fallback.

## License

This plugin is part of the me plugin collection.
