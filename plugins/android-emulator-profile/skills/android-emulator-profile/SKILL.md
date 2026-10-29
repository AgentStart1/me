---
name: android-emulator-profile
description: Use when viewing Android emulator status or screen previews, or creating or starting an Android Virtual Device (AVD) from a profile, including required SDK tool setup, system-image selection, Docker-friendly emulator launch, and the start-avd smoke test.
---

# Android Emulator Profile

## Project independence

Provision SDKs/AVDs and resolve this AI plugin's helpers in the operator environment. Do not add its installation paths, private provisioning profiles or launcher commands to project builds, CI or documentation merely to prepare an emulator. Projects may declare standard SDK/AVD requirements and use normal adb/test commands; Android Gradle plugins and required test libraries remain normal dependencies. Limit any explicitly requested AI-plugin integration to its requested scope.

## Bundled Paths

Paths resolve relative to this plugin root:

- `scripts/install-sdk.sh`
- `scripts/accept-sdk-licenses.sh`
- `scripts/create-avd.sh`
- `scripts/start-avd.sh`
- `scripts/profile-utils.sh`
- `tests/test-start-avd-docker.py`
- `tests/test-install-sdk.py`
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

Run the fake-command regression suite from this plugin directory in the `me` source checkout (requires the repository test helpers):

```bash
python tests/test-start-avd-docker.py
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
- `test-start-avd-docker.py` uses fake `emulator` and `adb` commands; it does not start Docker or a real emulator.
- Distinguish the host ADB server (5037) from the selected emulator's ADB endpoint
  (often 5555, but determined by its console/ADB port pair). Verify the VM route first;
  gvproxy's host alias can reach host loopback. Add a scoped port proxy/firewall rule
  only when the network actually needs one; do not restart shared proxy services blindly.

## Read-only status and screen preview

Call `android_emulator_status` to open the **Android Emulators** panel from the global sidebar or beside the conversation. It reads configured AVDs, ADB connectivity, and boot readiness without starting or resetting a device. If MCP Apps are unavailable, run `scripts/emulator_status.py` with Python 3 and summarize the JSON snapshot.

Screen capture is an explicit panel action through the app-only `android_emulator_screenshot` tool. Do not add automatic screenshot polling. A missing ADB connection is unavailable/unknown, not proof that every AVD stopped. Use `ANDROID_AVD_HOME` for an alternate inventory and `ANDROID_ADB_COMMAND` for an explicit ADB executable; see the owning README for all lookup rules.

## Upstream improvement feedback

- When using this plugin reveals an actionable bug, missing guidance, or reusable improvement, report it to [storytellerF/me](https://github.com/storytellerF/me/issues). Identify the owning plugin and skill; do not report project-specific problems without evidence that the plugin needs a change. Finish the user's primary task before non-blocking feedback work.
- Before any search or submission, reduce the finding to a privacy-safe summary. Never send raw conversations, private source code, logs, screenshots, credentials, personal identifiers, account data, or private paths/URLs. Use synthetic examples and the minimum non-sensitive environment details needed to explain the problem. If safe disclosure is impossible, keep the finding local.
- Search both open and closed upstream issues using the plugin name and sanitized symptom keywords. Read likely matches and their resolution; do not rely only on title matches. Reuse a matching issue link instead of opening a duplicate. Add a comment only when it supplies materially new, safe evidence and posting is authorized. A closed issue warrants a new report only for a distinct regression or uncovered case, with a link explaining the difference.
- Submit a new issue when no duplicate exists and the user has authorized upstream reporting in the current session or standing instructions. This rule alone does not authorize external posting. Honor existing authorization without asking again; otherwise prepare a sanitized draft for approval.
- Include the plugin/skill and version, observed and expected behavior, a minimal synthetic reproduction or concrete improvement proposal, and relevant duplicate-search results. Use a concise title prefixed with the plugin name.
- If search, authentication, or submission fails, retain the sanitized draft and explain the blocker; do not post without completing duplicate checks. After an uncertain submission result, check for the created issue before retrying. Return the existing or created issue URL, or clearly mark the report as an unsubmitted draft.

## Python profile controller

Run `python /absolute/plugin/scripts/start-avd.py /absolute/profile` directly
with Python 3.10+ on Windows or Unix. The shell startup entry only selects the
interpreter (`ANDROID_PROFILE_PYTHON` overrides lookup) and forwards arguments.
SDK installation remains Bash orchestration; its compatibility utilities use
the same Python profile parser, tool resolver and argument mapper. The native
startup controller owns AVD configuration updates.
Profiles remain literal data. Native Windows batch tools reject command
metacharacters and arguments ending in a backslash that cannot be safely forwarded; executable tools receive argument
lists. Use Ctrl+C or native Windows Ctrl+Break for graceful cancellation. Git
Bash `kill -TERM` forcibly terminates native Windows programs and cannot run
Python cleanup; inspect any remaining guard before recovery.

Profile configuration is read directly from the file, preserving key and option
case. AVD names, custom paths, emulator options, INI overrides and wipe permission
are not inherited from environment variables. Put these settings in the profile.
The shell creation entry keeps profile values in a separate map rather than
exporting them. Only `ANDROID_HOME`, `ANDROID_AVD_HOME`, `ANDROID_USER_HOME` and
the `EMULATOR_DISPLAY` to `DISPLAY` mapping are forwarded explicitly for Android
tools. Host PATH, HOME and profile/interpreter selection still use the environment.


Startup keeps its configuration guard until the whole owned command tree stops,
even if the command root exits first. If cleanup fails, leave the guard in place
and inspect the owning processes before recovery. Windows script tools use their
shebang interpreter through Git Bash. Device workers on Unix must stay in the
original process group; detached sessions are outside the launcher's ownership.

On Windows, the shared tool environment boundary converts inherited and profile
`ANDROID_HOME`, `ANDROID_AVD_HOME`, and `ANDROID_USER_HOME` paths from Git Bash
notation before launching native tools, so tools and configuration lookup use
the same directories. Empty values remain empty.

Read Git Bash path-conversion output as UTF-8, independent of the Windows ANSI
code page, so Unicode SDK and AVD directory names remain intact.
