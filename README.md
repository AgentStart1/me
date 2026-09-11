# me

A local Codex developer plugin collection. It includes Android tooling, client UI and coding guidance, test report sharing with ngrok tunnel support, plus a persistent pure-TCG QEMU Alpine Docker test environment for Windows.

## What is included

- Android emulator provisioning, profiles, and Appium device locking.
- Android, Kotlin, RecyclerView, client-UI, and general engineering guidance.
- Test-report and code-diff site generation with optional ngrok sharing.
- A persistent QEMU Alpine/Docker environment for Windows-hosted test runs.
- Portable Claude agent prompts bundled with their owning plugins.

Codex-compatible content is generated and synchronized automatically to the
standalone `me.codex` repository, which Codex users consume directly.

## Installation

### Codex

Codex users should follow the installation instructions in the dedicated
[`me.codex`](https://github.com/storytellerF/me.codex) repository.

### Claude Code

Add this GitHub repository as a Claude Code plugin marketplace:

```text
/plugin marketplace add storytellerF/me
```

Install plugins from the marketplace:

```text
/plugin install android-emulator-profile@me
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
