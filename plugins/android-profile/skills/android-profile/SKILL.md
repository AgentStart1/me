---
name: android-profile
description: Use the bundled Android SDK and AVD configuration scripts to install Android SDK tools, create Android Virtual Devices, launch Docker-friendly emulators, and run the start-avd smoke test.
---

# Android Profile

Use this skill when the task involves this plugin's Android SDK, AVD, emulator, or Docker smoke test scripts.

## Bundled Paths

Paths resolve relative to this plugin root:

- `scripts/install-sdk.sh`
- `scripts/accept-sdk-licenses.sh`
- `scripts/create-avd.sh`
- `scripts/start-avd.sh`
- `scripts/profile-utils.sh`
- `tests/test-start-avd-docker.sh`
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

Run the fake-command smoke test from the repository root:

```bash
tests/test-start-avd-docker.sh
```

## Configuration Rules

- When using a non-default profile, pass the profile path as the first argument.
- If no profile path is provided, `create-avd.sh` and `start-avd.sh` use `${ANDROID_PROFILE:-${ANDROID_PROFILE_DIR:-$HOME/android-profiles}/mobile.profile}`.
- When adding or checking `EMULATOR_FLAG_*` and `EMULATOR_VALUE_*` entries, use the official emulator command-line reference: https://developer.android.google.cn/studio/run/emulator-commandline
- `SYS_IMG_PKG` must be an Android system image package prefix without the ABI suffix.
- Scripts append the ABI based on the runtime architecture: `x86_64` uses `x86_64`, `aarch64` uses `arm64-v8a`.
- Do not define `ARCH`, `ABI`, `AVD_ARCH`, `AVD_ABI`, `AVDMANAGER_ABI`, `AVDMANAGER_ARCH`, `EMULATOR_ABI`, or `EMULATOR_ARCH` in profile files.

## Usage Notes

- Prefer running scripts from the plugin root so relative paths work naturally.
- Before running workflows that download SDK packages or start long-running emulator processes, ask the user first.
- `test-start-avd-docker.sh` uses fake `emulator` and `adb` commands; it does not start Docker or a real emulator.
- If the emulator runs on the host and a VM needs to access the host ADB port, prompt the user to set up `netsh interface portproxy` port forwarding on the host and add firewall rules allowing the VM subnet to access port `5555`.
