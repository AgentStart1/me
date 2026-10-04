# me

A portable [Agent Plugins](https://agent-plugins.org) collection. It includes Android tooling, client UI and coding guidance, test report sharing with ngrok tunnel support, plus a persistent pure-TCG QEMU Alpine Docker test environment for Windows.

## What is included

- Android emulator provisioning, profiles, and Appium device locking.
- Android, Kotlin, RecyclerView, client-UI, and general engineering guidance.
- Test-report and code-diff site generation with optional ngrok sharing.
- A persistent QEMU Alpine/Docker environment for Windows-hosted test runs.
- Portable Claude agent prompts bundled with their owning plugins.

This repository is the source of truth. Each `plugins/*/plugin.json` targets Agent Plugins 1.0.0; client metadata lives in reverse-domain `extensions`. Complete skill resources are shared. Claude-specific source routing and root-level agent prompts are retained for the Claude adapter; Codex generation removes routing fields only from generated copies.

GitHub Actions generates distribution pull requests in `me.claude` and `me.codex` after changes merge to `main`, or on manual dispatch. Install from those repositories.

## Installation

### Codex

Codex users should follow the installation instructions in the dedicated
[`me.codex`](https://github.com/storytellerF/me.codex) repository.

### Claude Code

Claude Code users should follow the installation and migration instructions in the dedicated
[`me.claude`](https://github.com/storytellerF/me.claude) repository.

## Development and synchronization

Run `bash scripts/build-claude-plugin-package.sh --all` and `bash scripts/build-codex-plugin-package.sh --all` to generate sibling directories. Inspect existing sibling checkouts first: generated `plugins/`, marketplace directories, and README are replaced; unrelated files are preserved. Do not commit or push generated repositories locally.

Run `python scripts/validate-plugin-packages.py --client claude ../me.claude` and `python scripts/validate-plugin-packages.py --client codex ../me.codex`, plus `bash tests/test-build-all-codex-plugins.sh` and `python tests/test-plugin-packages.py`. Validation dependencies are in `scripts/requirements-validation.txt`.

The sync workflow needs `UPSTREAM_GITHUB_TOKEN` with repository write and pull-request permissions for both existing destination repositories. It opens a separate generated PR for each client; destination PRs must merge before users receive updates. Start a new Codex thread after synchronized plugin updates are published and installed.

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
