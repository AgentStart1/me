# Manual Lock Lifecycle

Use manual acquisition when the test runner cannot use the bundled `run` command.

```bash
token_file="$(mktemp)"
plugins/android-appium-device-lock/scripts/adb-device-lock.sh acquire \
  --project-dir "$PWD" \
  --test-name "appium-login-suite" \
  --token-file "$token_file"

trap 'plugins/android-appium-device-lock/scripts/adb-device-lock.sh release --token-file "$token_file"' EXIT
npm run test:appium
```

Renew the lease periodically for long-running suites:

```bash
(
  while kill -0 "$$" 2>/dev/null; do
    sleep 1200
    plugins/android-appium-device-lock/scripts/adb-device-lock.sh renew \
      --token-file "$token_file" || break
  done
) &
renew_pid=$!
trap 'kill "$renew_pid" 2>/dev/null; plugins/android-appium-device-lock/scripts/adb-device-lock.sh release --token-file "$token_file"' EXIT
npm run test:long-suite
```

Release only with the token returned by acquisition. If renewal or release reports an owner-token mismatch, leave the lock intact because another run owns it.
