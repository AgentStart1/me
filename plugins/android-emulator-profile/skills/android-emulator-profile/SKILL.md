---
name: android-emulator-profile
description: Use when viewing Android emulator status or screen previews, or creating or starting an Android Virtual Device (AVD) from a profile, including required SDK tool setup, system-image selection, Docker-friendly emulator launch, and the start-avd smoke test.
---

# Android Emulator Profile

## Bundled Paths

Paths resolve relative to this plugin root:

- `scripts/install-sdk.sh`
- `scripts/accept-sdk-licenses.sh`
- `scripts/create-avd.sh`
- `scripts/start-avd.sh`
- `scripts/profile-utils.sh`
- `tests/test-start-avd-docker.sh`
- `tests/test-install-sdk.sh`
- `profiles/mobile.profile`
- `profiles/watch.profile`
- `profiles/tablet.profile`
- `profiles/desktop.profile`
- `profiles/tv.profile`

## Workflows

Install or update Android SDK tools:

```bash
ANDROID_HOME=${ANDROID_HOME:-$HOME/android-sdk} ./scripts/install-sdk.sh
```

Create a configured AVD:

```bash
./scripts/create-avd.sh ./profiles/mobile.profile
```

Start a configured emulator:

```bash
./scripts/start-avd.sh ./profiles/mobile.profile
```

Run the fake-command smoke test from the plugin root:

```bash
tests/test-start-avd-docker.sh
```

## Configuration Rules

- When using a non-default profile, pass the profile path as the first argument.
- If no profile path is provided, `create-avd.sh` and `start-avd.sh` use `${ANDROID_PROFILE:-${ANDROID_PROFILE_DIR:-$HOME/android-profiles}/mobile.profile}`.
- Check the installed tool's options against the [official command-line reference](https://developer.android.com/studio/run/emulator-commandline). Routine emulator management can use the current Android CLI when available; the bundled scripts implement the explicit profile/configuration workflow. Do not assume their flags can be transferred unchanged to another launcher.
- `SYS_IMG_PKG` must be an Android system image package prefix without the ABI suffix.
- Scripts append the ABI based on the runtime architecture: `x86_64` uses `x86_64`, `aarch64`/`arm64` use `arm64-v8a`; unsupported architectures fail before creation.
- Do not define `ARCH`, `ABI`, `AVD_ARCH`, `AVD_ABI`, `AVDMANAGER_ABI`, `AVDMANAGER_ARCH`, `EMULATOR_ABI`, or `EMULATOR_ARCH` in profile files.
- Profiles are literal data with an optional matching outer quote pair, never shell programs.
- Keep the AVD start guard and native locks intact during competing operations.
  Inspect interrupted guards/locks before recovery. Stop only the owned emulator process.
- Initialize a new AVD's partition size before its first userdata image. Resizing
  existing or custom userdata requires explicit `EMULATOR_ALLOW_DATA_WIPE=true`;
  do not enable that setting without authorization to erase that AVD's data.

## Usage Notes

- Resolve the installed plugin root from this skill location and use absolute script/profile paths. Keep the target project's working directory unchanged.
- Ensure SDK downloads and emulator startup are covered by the user's request or existing authorization; ask only if that scope is missing. Do not request approval again for an already authorized operation.
- `test-start-avd-docker.sh` uses fake `emulator` and `adb` commands; it does not start Docker or a real emulator.
- Distinguish the host ADB server (5037) from the selected emulator's ADB endpoint
  (often 5555, but determined by its console/ADB port pair). Verify the VM route first;
  gvproxy's host alias can reach host loopback. Add a scoped port proxy/firewall rule
  only when the network actually needs one; do not restart shared proxy services blindly.

## Read-only status and screen preview

Call `android_emulator_status` to open the **Android Emulators** panel from the global sidebar or beside the conversation. It reads configured AVDs, ADB connectivity, and boot readiness without starting or resetting a device. If MCP Apps are unavailable, run `scripts/emulator_status.py` with Python 3 and summarize the JSON snapshot.

Screen capture is an explicit panel action through the app-only `android_emulator_screenshot` tool. Do not add automatic screenshot polling. A missing ADB connection is unavailable/unknown, not proof that every AVD stopped. Use `ANDROID_AVD_HOME` for an alternate inventory and `ANDROID_ADB_COMMAND` for an explicit ADB executable; see the owning README for all lookup rules.
