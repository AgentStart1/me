# Android Device Lock

Serialize any Android device tests on physical devices or emulators, regardless of test framework, using the bundled `scripts/adb-device-lock.sh` helper. The device-side directory and token-checked lease remain the source of truth; see `skills/android-device-lock/SKILL.md` for acquisition, renewal, and release workflows.

## Device Leases status panel

Open **Device Leases** from a supporting MCP Apps host's thread tabs, or call `android_device_lock_status`. The read-only panel displays each ADB device's connectivity, lease state, task, project basename, owner host/PID, and remaining lease duration. Filter by device, serial, task, or owner; refresh manually or enable ten-second auto-refresh while visible.

States are deliberately distinct:

- **Free**: the device was reachable and no lock directory existed at observation time.
- **Held**: readable metadata contains an unexpired lease.
- **Expired**: the lease elapsed, but the lock directory still exists. The panel does not remove it.
- **Unknown/unavailable**: metadata is corrupt, the path is inaccessible, or the device cannot be queried. Treat ownership as unknown, not free.

The countdown uses the server's reported remaining duration and elapsed panel time. Reaching zero requests a refresh to verify ownership; it never automatically frees a device. The existing helper does not persist a waiting queue, so none is invented. Lease expiry follows the observing host's clock, matching the helper's timestamp basis.

Only allowlisted display fields leave the collector. `owner_token`, raw metadata, and full project paths are omitted. Observing the panel never acquires, renews, releases, or cleans up a lease, and it does not start a device test session.

## Local MCP runtime

Install [uv](https://docs.astral.sh/uv/) and make ADB available in the same environment as the local stdio MCP server. Compatibility manifests register `.mcp.json`:

```bash
uv run --script scripts/status-server.py
# JSON fallback:
python3 scripts/lock_status.py
```

ADB resolution honors `ANDROID_ADB_COMMAND`, PATH, `ANDROID_HOME`, `ANDROID_SDK_ROOT`, then `~/android-sdk`. ADB's usual server environment variables remain available; querying ADB may start its local server. All device reads use an explicit serial.

The plugin and skill now use the `android-device-lock` identifier. Replace the previous plugin installation with this package after publication. Finish existing test runs before switching to the new default lock path so all runners and the status collector use the same path. The inspected path defaults to `/data/local/tmp/android-device-test.lock.d`. For workflows using a custom `--lock-path`, set `ANDROID_DEVICE_LOCK_PATH` to that same absolute Android path. Shell quoting preserves spaces and special characters without evaluating the path as code.

The panel requires a host supporting MCP Apps and the OpenAI thread entrypoint. This change does not deploy a remote ChatGPT service. Shared UI build and test instructions live in the repository's `scripts/android-status/README.md`.

## Plugin packaging

`plugin.json` is the portable metadata source. Client manifests and complete skill resources are generated into `me.claude` and `me.codex`; install from those repositories. Source skills use portable frontmatter. Claude routing is stored in `extensions.com.anthropic.claude.skillFrontmatter`, keyed by skill directory, and injected only into generated Claude skills. Codex skill files are copied unchanged.
