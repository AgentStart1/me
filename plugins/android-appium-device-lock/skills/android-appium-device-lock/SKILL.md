---
name: android-appium-device-lock
description: Serialize Android Appium, UIAutomator, Espresso, or end-to-end test runs that share a single physical device or emulator by acquiring a device-side file lock before testing. Use when adding or running Android Appium tests, CI mobile tests, local adb-driven tests, or any workflow where only one app/test may control the same Android device at a time and other tests must wait for a lock with project directory, test name, start time, and timeout metadata.
context: fork
agent: android-e2e-operator
---

# Android Appium Device Lock

Use this skill whenever an Android test run may share a phone or emulator with other runs. Acquire a lock on the Android device before launching Appium or installing/running the app, and release it after the run finishes.

## Required Behavior

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

For manual acquire/release:

```bash
token_file="$(mktemp)"
plugins/android-appium-device-lock/scripts/adb-device-lock.sh acquire \
  --project-dir "$PWD" \
  --test-name "appium-login-suite" \
  --token-file "$token_file"

trap 'plugins/android-appium-device-lock/scripts/adb-device-lock.sh release --token-file "$token_file"' EXIT
npm run test:appium
```

For long-running test suites, renew the lock periodically to prevent expiry:

```bash
plugins/android-appium-device-lock/scripts/adb-device-lock.sh renew \
  --token-file "$token_file"
```

Typical renew loop pattern:

```bash
# renew in background every 20 minutes (default lease is 30 min)
(
  while kill -0 "$$" 2>/dev/null; do
    sleep 1200
    plugins/android-appium-device-lock/scripts/adb-device-lock.sh renew \
      --token-file "$token_file" || break
  done
) &
RENEW_PID=$!
trap 'kill "$RENEW_PID" 2>/dev/null; plugins/android-appium-device-lock/scripts/adb-device-lock.sh release --token-file "$token_file"' EXIT
npm run test:long-suite
```

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
