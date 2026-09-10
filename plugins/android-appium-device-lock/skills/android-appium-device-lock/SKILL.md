---
name: android-appium-device-lock
description: Use when adding or running Android UI or end-to-end tests with Appium, UIAutomator, Espresso, adb, CI mobile tests, or a physical device or emulator. Serialize device access with a device-side file lock so every test run is safe when the Android device is shared.
context: fork
agent: android-e2e-operator
---

# Android Appium Device Lock

## Required Behavior

- Acquire the device lock before launching Appium, installing or running the app, or changing device state.
- Store the lock on the device or emulator, not only on the host.
- Prefer an atomic lock directory plus a metadata file inside it. `adb shell mkdir <lockdir>` is atomic on the device and avoids check-then-write races.
- Include at least `project_dir`, `test_name`, `requested_at_utc`, `acquired_at_utc`, `max_timeout_seconds`, `expires_at_epoch`, `host`, `pid`, and `owner_token` in lock metadata.
- If a valid lock exists, wait and poll until it is released or expires.
- If the lock is expired, remove it and acquire a fresh lock.
- Always release the lock in a trap/finally block, and release only when the owner token matches.

## Quick Start

Use the bundled script for shell-based Appium workflows:

```bash
plugins/android-appium-device-lock/scripts/adb-device-lock.sh run \
  --serial "$ANDROID_SERIAL" \
  --project-dir "$PWD" \
  --test-name "appium-login-suite" \
  --max-timeout-seconds 1800 \
  --wait-timeout-seconds 3600 \
  -- npm run test:appium
```

For manual acquisition, release, and lease renewal, read
[`references/manual-lock-lifecycle.md`](references/manual-lock-lifecycle.md).

## Integration Guidance

- Put lock acquisition before `driver = webdriver.Remote(...)`, app install, app launch, or any step that changes device state.
- Scope the lock per adb device. Use `--serial` when multiple devices are connected.
- Keep `--max-timeout-seconds` slightly above the longest expected test duration so abandoned locks self-heal.
- Use a test-specific `--test-name` such as the CI job name, suite name, or local command name.
- Use the default lock path unless a project already standardizes another path. The default is `/data/local/tmp/appium-device-test.lock.d`, which is writable by `adb shell` on normal debug devices and emulators.
- In Node, Python, Java, or Gradle wrappers, either call the script as a subprocess or implement the same `mkdir lockdir -> write lock.json -> wait on existing lock -> token-checked release` sequence.

## Failure Handling

- If `adb` cannot see the device, fail before waiting for the lock.
- If lock metadata is malformed, treat the lock as active unless it can be proven expired by the directory mtime or by policy agreed in the project.
- If release fails because the token does not match, do not delete the lock; another run owns it.
- Do not clear app data, install APKs, start Appium sessions, or reset the emulator before acquiring the lock.

## Bundled Resource

- `scripts/adb-device-lock.sh`: deterministic adb lock helper with `acquire`, `release`, `renew`, and `run` commands.
