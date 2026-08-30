# me

A local Codex developer plugin collection. It includes Android tooling, client UI and coding guidance, test report sharing with ngrok tunnel support, plus a persistent pure-TCG QEMU Alpine Docker test environment for Windows.

## Package Structure

- `.agents/plugins/marketplace.json`: the in-repo `me` Codex marketplace entry.
- `plugins/android-profile/.codex-plugin/plugin.json`: Android Profile plugin manifest.
- `plugins/*/.claude-plugin/plugin.json`: Claude Code plugin manifests for compatible plugins.
- `plugins/android-profile/scripts/`: Android SDK, AVD, and emulator scripts.
- `plugins/android-profile/tests/`: smoke test scripts.
- `plugins/android-profile/profiles/android.profile`: default Android emulator profile.
- `plugins/android-profile/skills/android-profile/SKILL.md`: Codex-facing Android Profile instructions.
- `plugins/android-appium-device-lock/.codex-plugin/plugin.json`: Appium device lock plugin manifest.
- `plugins/android-appium-device-lock/scripts/adb-device-lock.sh`: adb-based device-side file lock script.
- `plugins/android-appium-device-lock/skills/android-appium-device-lock/SKILL.md`: Codex-facing Appium device lock instructions, including parent waiting for delegated device-verification reports.
- `plugins/recyclerview-best-practice/.codex-plugin/plugin.json`: RecyclerView best-practice plugin manifest.
- `plugins/recyclerview-best-practice/skills/`: RecyclerView adapter, diffing, paging, sentinel ViewHolder, and related practice instructions.
- `plugins/general-coding-practices/.codex-plugin/plugin.json`: General Coding Practices plugin manifest.
- `plugins/general-coding-practices/skills/`: project collaboration, README maintenance, flow stabilization before end-to-end test authoring, checks and tests, rule-file maintenance, logging, root-cause-first debugging, and repository synchronization instructions.
- `plugins/kotlin-coding-practices/.codex-plugin/plugin.json`: Kotlin Coding Practices plugin manifest.
- `plugins/kotlin-coding-practices/skills/`: coroutine-first, immutable-by-default Kotlin and Android Kotlin practice instructions.
- `plugins/client-ui-best-practices/.codex-plugin/plugin.json`: Client UI Best Practices plugin manifest.
- `plugins/client-ui-best-practices/skills/`: UI-thread boundaries, `hostScope`-confined Host work on a custom dispatcher, explicit Default/IO switching, Compose state collection, observable data, and UI-free business test guidance.
- `plugins/test-report-sharing/.claude-plugin/plugin.json`: Test Report Sharing plugin manifest.
- `plugins/test-report-sharing/skills/`: Test result collection, E2E recording capture, selectable Git/Difftastic diff report generation, and ngrok tunnel sharing.
- `plugins/test-report-sharing/scripts/`: Shell scripts for collecting test results, recordings, generating diffs, and starting ngrok.
- `plugins/qemu-alpine-docker/`: accelerated unattended Alpine/Docker provisioning, single-VM lifecycle, loopback Docker API and Testcontainers port-range forwarding.
- `plugins/*/agents/`: portable agent prompts at the plugin root, alongside `skills/`.
- `agents/`: prompts specific to maintaining this plugin collection.

## Installation

### Codex

Add this GitHub repository as a Codex plugin marketplace:

```bash
codex plugin marketplace add https://github.com/storytellerF/me
```

Install plugins from the marketplace:

```bash
codex plugin add android-profile@me
codex plugin add android-appium-device-lock@me
codex plugin add recyclerview-best-practice@me
codex plugin add general-coding-practices@me
codex plugin add kotlin-coding-practices@me
codex plugin add client-ui-best-practices@me
codex plugin add test-report-sharing@me
codex plugin add qemu-alpine-docker@me
```

Start a new Codex thread after installation so the plugin skills are loaded.

### Claude Code

Add this GitHub repository as a Claude Code plugin marketplace:

```text
/plugin marketplace add storytellerF/me
```

Install plugins from the marketplace:

```text
/plugin install android-profile@me
/plugin install android-appium-device-lock@me
/plugin install recyclerview-best-practice@me
/plugin install general-coding-practices@me
/plugin install kotlin-coding-practices@me
/plugin install client-ui-best-practices@me
/plugin install test-report-sharing@me
/plugin install qemu-alpine-docker@me
```

Run `/reload-plugins` after installation to load the installed plugins in the current Claude Code session.

### Agent prompts

Claude Code loads the Markdown agents from each plugin's root `agents/` directory. The repository
also maintains `agents/me-agent-config-maintainer.md` for prompts specific to this collection.

## Running Scripts Directly

You can also run the bundled scripts directly from the plugin root:

```bash
cd plugins/android-profile
ANDROID_HOME=$HOME/android-sdk ./scripts/install-sdk.sh
./scripts/create-avd.sh ./profiles/android.profile
./scripts/start-avd.sh ./profiles/android.profile
```

Custom profiles may define standard Android path variables directly, including `ANDROID_HOME`, `ANDROID_AVD_HOME`, and `ANDROID_USER_HOME`. The scripts load the profile first, then locate SDK tools and AVD files. The bundled `profiles/android.profile` does not preset these paths.

Run the `start-avd.sh` smoke test with fake emulator commands from the repository root:

```bash
plugins/android-profile/tests/test-start-avd-docker.sh
```

Provision and run the persistent Alpine Docker test VM from Git Bash or MSYS2:

```bash
cd plugins/qemu-alpine-docker
./scripts/setup.sh
./scripts/create-vm.sh ./profiles/dev.profile
./scripts/start-vm.sh ./profiles/dev.profile
./scripts/run-testcontainers.sh -- <test command>
```

## Host Emulator Access From a VM

If the Android emulator runs on the host machine and a VM needs to access the host ADB port, add port forwarding and firewall rules on the host. This example assumes the VM subnet is `192.168.80.0/24` and the host address on that virtual network is `192.168.80.1`:

```powershell
netsh interface portproxy add v4tov4 listenaddress=192.168.80.1 listenport=5555 connectaddress=127.0.0.1 connectport=5555
netsh advfirewall firewall add rule name="Android Emulator ADB 5555" dir=in action=allow protocol=TCP localport=5555 remoteip=192.168.80.0/24
```

Confirm the port proxy entry exists:

```shell
netsh interface portproxy show all
```

Confirm the host is listening:

```shell
netstat -ano | findstr "192.168.80.1:5555"
```

If it is not listening, restart the service:

```shell
net stop iphlpsvc
net start iphlpsvc
```
