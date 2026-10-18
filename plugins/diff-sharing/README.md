# Diff Sharing Plugin

Generate a Difftastic-first Git diff site and share it through ngrok. Git remains available as a fallback renderer when `difft` is unavailable.

## Workflow

```bash
plugins/diff-sharing/scripts/generate-diff-report.sh
plugins/diff-sharing/scripts/generate-diff-site.sh
plugins/diff-sharing/scripts/start-ngrok.sh
```

When `difft` is on `PATH`, the generated page opens with Difftastic selected. Otherwise it defaults to Git diff and marks Difftastic unavailable.

For an installed plugin, resolve scripts by absolute path and invoke them from
any directory inside the Git repository. All commands automatically use its root. `start-ngrok.sh --local-only` serves the report on loopback. The
normal launcher also stays local if ngrok is absent or fails to authenticate, using
saved ngrok credentials or `NGROK_AUTHTOKEN` when available. Keep the launcher running
while using the URL; Ctrl+C stops only its own server and tunnel.

The `.sh` files are thin compatibility launchers. Every command also has a same-named `.py` entrypoint, for example `python /path/to/plugin/scripts/start-ngrok.py --local-only`. Generation, site assembly and serving share a cache keyed by the Git repository root, including when invoked from different subdirectories.

Default cache keys now use the native Python project path. Regenerate reports
after upgrading, or pass the same explicit `--output-dir` to reuse an older cache.

Statistics, Git patches and Difftastic always compare the same repository-wide
scope. Submodule changes are excluded from all three. Committed comparisons use
only the selected Git history; deleted files remain empty on the deleted side,
even when a same-named file exists in the current working tree.

Explicit relative `--output-dir` and `REPORT_OUTPUT_DIR` paths are resolved from
the original calling directory before entering the repository root.

## Configuration

| Variable | Description | Default |
|---|---|---|
| `REPORT_OUTPUT_DIR` | Output directory for generated artifacts | `~/.cache/diff-reports/<project-hash>` |
| `NGROK_AUTHTOKEN` | ngrok token override | Saved credentials when unset |
| `NGROK_PORT` | Local port to expose | `8080` |
| `PYTHON_COMMAND` | Python 3.10+ executable used by all commands | `python3`, then `python` |
| `GIT_BASE_REF` | Base Git ref | `main` |
| `GIT_COMPARE_REF` | Compare Git ref | `HEAD` |
| `GIT_INCLUDE_UNCOMMITTED` | Include uncommitted changes | `true` |
| `DIFFTASTIC_COMMAND` | Difftastic executable name or path | `difft` |
| `DIFFTASTIC_WIDTH` | Captured Difftastic output width | `160` |
| `DIFFTASTIC_SKIP_UNCHANGED` | Omit unchanged files | `true` |
| `DIFFTASTIC_PARSE_ERROR_LIMIT` | Parse errors before text fallback | `100` |

## Requirements

- **Bash** for the compatibility `.sh` launchers; native Python entrypoints also work without Bash.
- **Git** for code-diff sharing.
- **Difftastic (`difft`)** for the preferred structural renderer.
- **ngrok** for public sharing; otherwise use the local server URL.
- **Python 3.10+** for all report and preview commands. Shell launchers check `python3`, then `python`; `PYTHON_COMMAND` overrides interpreter selection.

## License

This plugin is part of the me plugin collection.

## Plugin packaging

`plugin.json` is the portable metadata source. Client manifests and complete skill resources are generated into `me.claude` and `me.codex`; install from those repositories. Source skills use portable frontmatter. Claude routing is stored in `extensions.com.anthropic.claude.skillFrontmatter`, keyed by skill directory, and injected only into generated Claude skills. Codex skill files are copied unchanged.

## Improvement feedback

Plugin findings go to [storytellerF/me issues](https://github.com/storytellerF/me/issues). Skills require checking open and closed issues before reporting, using sanitized or synthetic examples, and honoring the user's authorization before posting. Existing reports are reused; unavailable access leaves an unsubmitted draft.
