# Android Emulator Profile Plugin

This plugin provides profile-driven Android Virtual Device creation and emulator startup for local and Docker-friendly environments.

## Included tooling

- Install Android SDK command-line tools and accept licenses.
- Create AVDs from mobile, tablet, desktop, TV, and watch profiles.
- Start emulators with architecture-aware defaults.
- Run a fake-command smoke test without starting a real emulator.

Use Bash 4.3+ and GNU-compatible shell utilities for these scripts. Resolve their
absolute paths from the installed plugin root; supplied profiles are literal data.
The SDK installer downloads outside the project directory, respects existing SDK
ownership and keeps replaced tools in a `cmdline-tools/previous.*` directory. Its
bundled command-line-tools release is a minimum setup choice, not a claim to always
download the latest upstream release; newer installed tools are reused.

Emulator startup preserves existing `DISPLAY` unless the profile overrides it.
It refuses an occupied/interrupted AVD start guard or native lock, and shutdown
targets only the process it launched. Confirm all owners have stopped before manual
lock recovery. A new AVD can set its partition size before first boot; resizing
existing or custom userdata requires explicit `EMULATOR_ALLOW_DATA_WIPE=true`.
This setting authorizes a destructive reset of that AVD and should not be a routine default.

For ordinary device management, consult the current [Android CLI guidance](https://developer.android.com/studio/run/emulator-commandline).
The bundled scripts remain available for the profile/configuration workflow; check
installed emulator flags rather than assuming every SDK version supports them.

## Android Emulators status panel

Open **Android Emulators** from a supporting MCP Apps host's global sidebar or thread tabs, or call `android_emulator_status`. The read-only panel lists configured AVDs and connected emulators, including boot readiness, serial, Android/API version, ABI, configured memory, and resolution. It supports filtering, manual refresh, and optional ten-second auto-refresh while visible. Failed probes remain unknown or unavailable. A configured AVD without an observed ADB connection is marked disconnected; that does not assert that its process stopped.

**Capture screen** is available for booted emulators. Each click calls the app-only `android_emulator_screenshot` tool with an explicit serial. It captures one PNG through `adb exec-out screencap -p`; refresh does not capture screens, no screenshot is saved on the device, and physical phones are rejected. Closing the preview discards the displayed image. The panel does not start, stop, reset, or unlock an emulator.

Install [uv](https://docs.astral.sh/uv/) and make ADB available in the same environment as the MCP server. The manifests register the local stdio service automatically in compatible hosts:

```bash
uv run --script scripts/status-server.py
# JSON fallback when the host cannot render MCP Apps:
python3 scripts/emulator_status.py
```

ADB resolution honors `ANDROID_ADB_COMMAND`, PATH, `ANDROID_HOME`, `ANDROID_SDK_ROOT`, then `~/android-sdk`. ADB's usual server environment variables remain available; invoking ADB may start its local server. AVD inventory honors `ANDROID_AVD_HOME` or `ANDROID_USER_HOME`, falling back to `~/.android/avd`. It reads existing `.ini` files and never evaluates profiles or rewrites configuration. TCP-connected emulators are identified by the Android QEMU property; an offline TCP device cannot be conclusively classified as an emulator. Unmapped/offline emulator instances prevent unknown local AVDs from being reported as disconnected.

Native rendering requires MCP Apps and OpenAI thread-entrypoint support. This is a local MCP service, not a deployed remote ChatGPT application. See the repository's `scripts/android-status/README.md` for shared UI build and validation instructions.

## Plugin packaging

`plugin.json` is the portable metadata source. Client manifests and complete skill resources are generated into `me.claude` and `me.codex`; install from those repositories. Source skills use portable frontmatter. Claude routing is stored in `extensions.com.anthropic.claude.skillFrontmatter`, keyed by skill directory, and injected only into generated Claude skills. Codex skill files are copied unchanged.
