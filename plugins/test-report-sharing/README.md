# Test Report Sharing Plugin

Collect test reports, then share a static report site through ngrok.

## Workflow

```bash
plugins/test-report-sharing/scripts/collect-test-results.sh
plugins/test-report-sharing/scripts/generate-report-site.sh
plugins/test-report-sharing/scripts/start-ngrok.sh
```

`test-report-operator` coordinates the same workflow when Claude agent routing is available.

For an installed plugin, use absolute script paths. Every command accepts
`--project-dir DIR`, defaulting to the current directory. It is the base for report
searches, relative custom report directories and the default cache. Collection discovers HTML roots and nested JUnit XML
up to four directory levels below each search root. Overlapping HTML roots are
deduplicated; same-named XML from different paths are retained separately and linked
from the site. Keep the output outside a report being copied.

`start-ngrok.sh --local-only` serves the site on `127.0.0.1`. The normal launcher
also stays local if ngrok is absent or authentication fails. Credentials may come
from saved configuration or `NGROK_AUTHTOKEN`. Keep the launcher running while using
its URL; Ctrl+C stops only that launcher's server and tunnel.

The `.sh` files are thin compatibility launchers. Every command also has a same-named `.py` entrypoint, for example `python /path/to/plugin/scripts/start-ngrok.py --local-only`. Use the same `--project-dir` for collection, site assembly and serving to share the default cache.

Default cache keys now use the native Python project path. Regenerate reports
after upgrading, or pass the same explicit `--output-dir` to reuse an older cache.

```bash
python /path/to/plugin/scripts/collect-test-results.py --project-dir /path/to/project
python /path/to/plugin/scripts/generate-report-site.py --project-dir /path/to/project
python /path/to/plugin/scripts/start-ngrok.py --project-dir /path/to/project --local-only
```

Explicit relative `--output-dir` and `REPORT_OUTPUT_DIR` paths are resolved from
the original calling directory. Registered submodule directories are excluded
from scans and copied report trees, including explicitly supplied search roots.
Git is required when collecting from Git repositories so registered submodules
can be identified. Non-Git projects do not require Git. Use a fresh output directory for reports collected by older
versions that did not exclude submodules.

## Configuration

| Variable | Description | Default |
|---|---|---|
| `REPORT_OUTPUT_DIR` | Output directory for collected reports | `~/.cache/test-reports/<project-hash>` |
| `TEST_RESULT_DIRS` | Legacy colon-separated report directories; `REPORT_DIRS` is an alias. Use repeated `--test-dir DIR` for Windows drive paths | Auto-detect HTML/JUnit locations |
| `NGROK_AUTHTOKEN` | ngrok token override | Saved credentials when unset |
| `NGROK_PORT` | Local port to expose | `8080` |
| `PYTHON_COMMAND` | Python 3.10+ executable used by all commands | `python3`, then `python` |

## Requirements

- **Bash** for the compatibility `.sh` launchers; native Python entrypoints also work without Bash.
- **ngrok** for public sharing; otherwise use the local server URL.
- **Python 3.10+** for all report and preview commands; no third-party Python packages are required.

## License

This plugin is part of the me plugin collection.

## Plugin packaging

`plugin.json` is the portable metadata source. Client manifests and complete skill resources are generated into `me.claude` and `me.codex`; install from those repositories. Source skills use portable frontmatter. Claude routing is stored in `extensions.com.anthropic.claude.skillFrontmatter`, keyed by skill directory, and injected only into generated Claude skills. Codex skill files are copied unchanged.

## Improvement feedback

Plugin findings go to [storytellerF/me issues](https://github.com/storytellerF/me/issues). Skills require checking open and closed issues before reporting, using sanitized or synthetic examples, and honoring the user's authorization before posting. Existing reports are reused; unavailable access leaves an unsubmitted draft.


Each collection publishes a complete replacement snapshot, including its site.
Repeating collection does not duplicate reports in the current view; removed
source reports disappear from the next snapshot. Failed collection leaves the
previous version available. Use the launcher URL for the latest snapshot; open
pages keep their original assets. Older generations are retained, so remove the
dedicated report cache only after its servers and readers have finished.

Linked assets are copied into each snapshot, so later source changes do not alter
open reports. Cyclic directory links fail collection and preserve the previous version.
