# me

A local Codex developer plugin collection. It includes Android tooling, client UI and coding guidance, test report sharing with ngrok tunnel support, plus a persistent pure-TCG QEMU Alpine Docker test environment for Windows.

## What is included

- Android emulator provisioning, profiles, and Appium device locking.
- Android, Kotlin, RecyclerView, client-UI, and general engineering guidance.
- Test-report and code-diff site generation with optional ngrok sharing.
- A persistent QEMU Alpine/Docker environment for Windows-hosted test runs.
- Portable Claude agent prompts bundled with their owning plugins.

Codex-compatible content is generated directly into the standalone sibling
repository `../me.codex`, which is the repository used by Codex users.

## Installation

### Codex

Use the dedicated [`me.codex`](https://github.com/AgentStart1/me.codex)
repository as the Codex marketplace. From a clone of that repository:

```bash
codex plugin marketplace add .
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
codex plugin add diff-sharing@me
codex plugin add qemu-alpine-docker@me
```

Start a new Codex thread after installation so the plugin skills are loaded.

### Updating the Codex repository

Develop and review plugin source changes in this repository. Once the branch is
ready, clone `me.codex` next to this repository and regenerate its contents:

```bash
scripts/build-codex-plugin-package.sh --all
git -C ../me.codex diff
```

The generator replaces `me.codex`'s generated `README.md`, `.agents/plugins/`,
and `plugins/` paths while preserving `.git` and unrelated paths. Existing
changes in `me.codex` do not block regeneration. Review and commit the result
there, then open the upstream PR from that repository.

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
/plugin install diff-sharing@me
/plugin install qemu-alpine-docker@me
```

Run `/reload-plugins` after installation to load the installed plugins in the current Claude Code session.

### Agent prompts

Claude Code loads the Markdown agents from each plugin's root `agents/` directory.

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
