---
name: android-device-lock
description: Use when viewing Android device lock ownership or lease status, or running any Android device tests on a shared physical device or emulator, regardless of test framework. Serialize device access with a device-side adb file lock.
---

# Android Device Lock

Use this plugin for any Android device test that needs exclusive access, including UI, instrumentation, end-to-end, and adb-driven tests. The test framework does not affect the locking workflow.

## Project-independent execution

The plugin manages device access outside the target project. Acquire the lock through the installed plugin, run the project's existing test command unchanged from its original working directory, then release the lock.

- Resolve the installed plugin root from the loaded skill location: this skill is at `<plugin-root>/skills/android-device-lock/SKILL.md`. Use the absolute path to `<plugin-root>/scripts/adb-device-lock.sh`; never assume the project contains a `plugins/` directory.
- Do not copy, vendor, generate, or reimplement the lock helper in the target project. Do not add lock dependencies, test wrappers, build changes, CI configuration, or project documentation merely to use the plugin. Project integration requires a separate explicit user request.
- Keep owner-token files and any temporary orchestration outside the project, using the system temporary directory. `project_dir` and `test_name` identify the lease owner only; they do not configure the project or select a separate lock.
- All projects using the same adb device must use the same device-side lock path. Use the bundled default. An existing non-default path must be shared by every participant and the status collector; do not choose a path per project.
- If the installed helper cannot be located, report the unavailable plugin resource instead of copying it into the project or implementing a replacement.

## Required Behavior

- Acquire the device lock before starting a device test session, installing or running the app, or changing device state.
- Store the lock on the device or emulator, not only on the host.
- Use the bundled helper’s atomic lock directory and metadata file. `adb shell mkdir <lockdir>` is atomic on the device and avoids check-then-write races.
- Include at least `project_dir`, `test_name`, `requested_at_utc`, `acquired_at_utc`, `max_timeout_seconds`, `expires_at_epoch`, `host`, `pid`, and `owner_token` in lock metadata.
- If a valid lock exists, wait and poll until it is released or expires.
- If the lock is expired, remove it and acquire a fresh lock.
- Always release the lock in a trap/finally block, and release only when the owner token matches.

## Quick Start

Run from the target project directory. Here `DEVICE_LOCK_PLUGIN_ROOT` is a session-local absolute path resolved from the loaded skill location, not a project setting:

```bash
"$DEVICE_LOCK_PLUGIN_ROOT/scripts/adb-device-lock.sh" run \
  --serial "$ANDROID_SERIAL" \
  --project-dir "$PWD" \
  --test-name "android-device-suite" \
  --max-timeout-seconds 1800 \
  --wait-timeout-seconds 3600 \
  -- ./gradlew connectedAndroidTest
```

For manual acquisition, release, and lease renewal, read
[`references/manual-lock-lifecycle.md`](references/manual-lock-lifecycle.md).

## Execution Guidance

The helper handles Git Bash-to-Windows ADB path conversion: Android paths remain unchanged, while local metadata upload paths are converted with `cygpath` when available.

- Put lock acquisition before test-session creation, app install, app launch, or any step that changes device state.
- Scope the lock per adb device. Use `--serial` when multiple devices are connected.
- Keep `--max-timeout-seconds` slightly above the longest expected test duration so abandoned locks self-heal.
- Use a test-specific `--test-name` such as the CI job name, suite name, or local command name.
- The shared default lock path is `/data/local/tmp/android-device-test.lock.d`, which is writable by `adb shell` on normal debug devices and emulators.
- If one command cannot cover the complete device operation, use the manual lifecycle from an agent-owned temporary shell session, without editing the project test runner.

## Failure Handling

- If `adb` cannot see the device, fail before waiting for the lock.
- If lock metadata is malformed, treat the lock as active unless it can be proven expired by the directory mtime under the shared device-lock policy.
- If release fails because the token does not match, do not delete the lock; another run owns it.
- Do not clear app data, install APKs, start device test sessions, or reset the emulator before acquiring the lock.

## Bundled Resource

- `scripts/adb-device-lock.sh`: deterministic adb lock helper with `acquire`, `release`, `renew`, and `run` commands.

## Read-only lease status

For requests to view device occupancy, current owner, task, or expiry, call `android_device_lock_status` to open **Device Leases** from the global sidebar or beside the conversation. Observation requires no acquisition or release. If MCP Apps are unavailable, run `scripts/lock_status.py` with Python 3 and summarize its JSON snapshot.

Never disclose the owner token in tool results or UI. Expired metadata means a stale lease is still present, not that the panel has released the device. Offline devices and unreadable metadata must remain unknown/unavailable. The helper has no durable waiting queue, so do not invent waiting-task data. For custom lock locations, set `ANDROID_DEVICE_LOCK_PATH` to the same path used by `--lock-path`.
