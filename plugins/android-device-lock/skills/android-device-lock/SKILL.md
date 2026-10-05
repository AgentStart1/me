---
name: android-device-lock
description: Use when viewing Android device lock ownership or lease status, or adding or running any Android device tests on a shared physical device or emulator, regardless of test framework. Serialize device access with a device-side adb file lock.
---

# Android Device Lock

Use this plugin for any Android device test that needs exclusive access, including UI, instrumentation, end-to-end, and adb-driven tests. The test framework does not affect the locking workflow.

## Required Behavior

- Acquire the device lock before starting a device test session, installing or running the app, or changing device state.
- Store the lock on the device or emulator, not only on the host.
- Prefer an atomic lock directory plus a metadata file inside it. `adb shell mkdir <lockdir>` is atomic on the device and avoids check-then-write races.
- Include at least `project_dir`, `test_name`, `requested_at_utc`, `acquired_at_utc`, `max_timeout_seconds`, `expires_at_epoch`, `host`, `pid`, and `owner_token` in lock metadata.
- If a valid lock exists, wait and poll until it is released or expires.
- If the lock is expired, remove it and acquire a fresh lock.
- Always release the lock in a trap/finally block, and release only when the owner token matches.

## Quick Start

Use the bundled script for any shell-based Android device test workflow:

```bash
plugins/android-device-lock/scripts/adb-device-lock.sh run \
  --serial "$ANDROID_SERIAL" \
  --project-dir "$PWD" \
  --test-name "android-device-suite" \
  --max-timeout-seconds 1800 \
  --wait-timeout-seconds 3600 \
  -- ./gradlew connectedAndroidTest
```

For manual acquisition, release, and lease renewal, read
[`references/manual-lock-lifecycle.md`](references/manual-lock-lifecycle.md).

## Integration Guidance

- Put lock acquisition before test-session creation, app install, app launch, or any step that changes device state.
- Scope the lock per adb device. Use `--serial` when multiple devices are connected.
- Keep `--max-timeout-seconds` slightly above the longest expected test duration so abandoned locks self-heal.
- Use a test-specific `--test-name` such as the CI job name, suite name, or local command name.
- Use the default lock path unless a project already standardizes another path. The default is `/data/local/tmp/android-device-test.lock.d`, which is writable by `adb shell` on normal debug devices and emulators.
- In Node, Python, Java, or Gradle wrappers, either call the script as a subprocess or implement the same `mkdir lockdir -> write lock.json -> wait on existing lock -> token-checked release` sequence.

## Failure Handling

- If `adb` cannot see the device, fail before waiting for the lock.
- If lock metadata is malformed, treat the lock as active unless it can be proven expired by the directory mtime or by policy agreed in the project.
- If release fails because the token does not match, do not delete the lock; another run owns it.
- Do not clear app data, install APKs, start device test sessions, or reset the emulator before acquiring the lock.

## Bundled Resource

- `scripts/adb-device-lock.sh`: deterministic adb lock helper with `acquire`, `release`, `renew`, and `run` commands.

## Read-only lease status

For requests to view device occupancy, current owner, task, or expiry, call `android_device_lock_status` to open **Device Leases**. Observation requires no acquisition or release. If MCP Apps are unavailable, run `scripts/lock_status.py` with Python 3 and summarize its JSON snapshot.

Never disclose the owner token in tool results or UI. Expired metadata means a stale lease is still present, not that the panel has released the device. Offline devices and unreadable metadata must remain unknown/unavailable. The helper has no durable waiting queue, so do not invent waiting-task data. For custom lock locations, set `ANDROID_DEVICE_LOCK_PATH` to the same path used by `--lock-path`.
