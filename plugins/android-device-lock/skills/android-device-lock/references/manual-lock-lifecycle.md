# Manual Lock Lifecycle

Use manual acquisition from an agent-owned shell session when device operations span several commands. Resolve `DEVICE_LOCK_PLUGIN_ROOT` to the installed plugin’s absolute root as described in `SKILL.md`; keep the project’s test runner and CI unchanged. Run the existing test command from the project directory and store token files in the system temporary directory.

```bash
token_file="$(mktemp)"
"$DEVICE_LOCK_PLUGIN_ROOT/scripts/adb-device-lock.sh" acquire \
  --serial "$ANDROID_SERIAL" \
  --project-dir "$PWD" \
  --test-name "android-device-suite" \
  --token-file "$token_file"

trap '"$DEVICE_LOCK_PLUGIN_ROOT/scripts/adb-device-lock.sh" release --serial "$ANDROID_SERIAL" --token-file "$token_file"' EXIT
./gradlew connectedAndroidTest
```

Renew the lease periodically for long-running suites:

```bash
"$DEVICE_LOCK_PLUGIN_ROOT/scripts/adb-device-lock.sh" renew \
  --serial "$ANDROID_SERIAL" \
  --token-file "$token_file" \
  --max-timeout-seconds 1800
```

Remove the temporary token file after releasing the lease. Release only with the token returned by acquisition. If renewal or release reports an owner-token mismatch, leave the lock intact because another run owns it.

Renew before expiry throughout the operation. An automatic renewer must have the
same lifetime as its test command and stop device work on renewal failure; merely
exiting a background renewal loop while the test continues loses exclusivity.
The helper's `run` mode does not automatically extend its lease. Keep acquisition,
renewal and release on the same serial and lock path; include `--serial` in the
acquisition/release examples when more than one device is connected.
