# Manual Lock Lifecycle

Use manual acquisition from an agent-owned shell session when device operations span several commands. Resolve `DEVICE_LOCK_PLUGIN_ROOT` to the installed plugin’s absolute root as described in `SKILL.md`; keep the project’s test runner and CI unchanged. Run the existing test command from the project directory and store token files in the system temporary directory.

```bash
token_file="$(mktemp)"
"$DEVICE_LOCK_PLUGIN_ROOT/scripts/adb-device-lock.sh" acquire \
  --project-dir "$PWD" \
  --test-name "android-device-suite" \
  --token-file "$token_file"

trap '"$DEVICE_LOCK_PLUGIN_ROOT/scripts/adb-device-lock.sh" release --token-file "$token_file"' EXIT
./gradlew connectedAndroidTest
```

Renew the lease periodically for long-running suites:

```bash
(
  while kill -0 "$$" 2>/dev/null; do
    sleep 1200
    "$DEVICE_LOCK_PLUGIN_ROOT/scripts/adb-device-lock.sh" renew \
      --token-file "$token_file" || break
  done
) &
renew_pid=$!
trap 'kill "$renew_pid" 2>/dev/null; "$DEVICE_LOCK_PLUGIN_ROOT/scripts/adb-device-lock.sh" release --token-file "$token_file"' EXIT
npm run test:long-suite
```

Remove the temporary token file after releasing the lease. Release only with the token returned by acquisition. If renewal or release reports an owner-token mismatch, leave the lock intact because another run owns it.
