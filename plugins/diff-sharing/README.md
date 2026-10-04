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
| `PYTHON_COMMAND` | Python 3 executable used by the local server | `python3`, then `python` |
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
- **Python 3** for the local HTTP-server fallback. The launcher asks `python3` and then `python` to execute a Python 3 version check, skipping Python 2 and non-functional command aliases such as the Windows Store placeholder.

## License

This plugin is part of the me plugin collection.

## Plugin packaging

`plugin.json` is the portable metadata source. Client manifests and complete skill resources are generated into `me.claude` and `me.codex`; install from those repositories. Source skills use portable frontmatter. Claude routing is stored in `extensions.com.anthropic.claude.skillFrontmatter`, keyed by skill directory, and injected only into generated Claude skills. Codex skill files are copied unchanged.
