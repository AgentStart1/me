# Android Emulator Profile Plugin

This plugin provides profile-driven Android Virtual Device creation and emulator startup for local and Docker-friendly environments.

## Included tooling

- Install Android SDK command-line tools and accept licenses.
- Create AVDs from mobile, tablet, desktop, TV, and watch profiles.
- Start emulators with architecture-aware defaults.
- Run a fake-command smoke test without starting a real emulator.

## Android Emulators status panel

Open **Android Emulators** from a supporting MCP Apps host's thread tabs, or call `android_emulator_status`. The read-only panel lists configured AVDs and connected emulators, including boot readiness, serial, Android/API version, ABI, configured memory, and resolution. It supports filtering, manual refresh, and optional ten-second auto-refresh while visible. Failed probes remain unknown or unavailable. A configured AVD without an observed ADB connection is marked disconnected; that does not assert that its process stopped.

**Capture screen** is available for booted emulators. Each click calls the app-only `android_emulator_screenshot` tool with an explicit serial. It captures one PNG through `adb exec-out screencap -p`; refresh does not capture screens, no screenshot is saved on the device, and physical phones are rejected. Closing the preview discards the displayed image. The panel does not start, stop, reset, or unlock an emulator.

Install [uv](https://docs.astral.sh/uv/) and make ADB available in the same environment as the MCP server. The manifests register the local stdio service automatically in compatible hosts:

```bash
uv run --script scripts/status-server.py
# JSON fallback when the host cannot render MCP Apps:
python3 scripts/emulator_status.py
```

ADB resolution honors `ANDROID_ADB_COMMAND`, PATH, `ANDROID_HOME`, `ANDROID_SDK_ROOT`, then `~/android-sdk`. ADB's usual server environment variables remain available; invoking ADB may start its local server. AVD inventory honors `ANDROID_AVD_HOME` or `ANDROID_USER_HOME`, falling back to `~/.android/avd`. It reads existing `.ini` files and never evaluates profiles or rewrites configuration. TCP-connected emulators are identified by the Android QEMU property; an offline TCP device cannot be conclusively classified as an emulator. Unmapped/offline emulator instances prevent unknown local AVDs from being reported as disconnected.

Native rendering requires MCP Apps and OpenAI thread-entrypoint support. This is a local MCP service, not a deployed remote ChatGPT application. See the repository's `scripts/android-status/README.md` for shared UI build and validation instructions.
