# me

A portable [Agent Plugins](https://agent-plugins.org) collection. It includes Android tooling, client UI and coding guidance, test report sharing with ngrok tunnel support, plus a persistent QEMU Alpine Docker environment for Linux Docker containers and Windows.

## What is included

- Android emulator provisioning, profiles, and framework-independent Android device test locking.
- Android, Kotlin, RecyclerView, client-UI, and general engineering guidance.
- Test-report and code-diff site generation with optional ngrok sharing.
- A persistent QEMU Alpine/Docker environment with Linux KVM, Windows WHPX, and portable TCG fallback, for Linux Docker container and Windows workflows. Linux hosts outside containers can use Docker directly without this plugin.
- Portable Claude agent prompts bundled with their owning plugins.

This repository is the source of truth. Each `plugins/*/plugin.json` targets Agent Plugins 1.0.0; client metadata lives in reverse-domain `extensions`. Complete skill resources are shared. Source skills use portable frontmatter so other Agent Plugins clients can load them directly. Claude routing is stored in `extensions.com.anthropic.claude.skillFrontmatter`, keyed by skill directory, and injected only when generating `me.claude`. Codex skill files are copied unchanged. Reusable agent prompts remain at each plugin’s `agents/` directory.

GitHub Actions generates distribution pull requests in `me.claude` and `me.codex` after changes merge to `main`, or on manual dispatch. Install from those repositories.

## Improvement feedback

Every plugin's skills include an upstream feedback workflow for actionable plugin improvements. Reports target [storytellerF/me](https://github.com/storytellerF/me/issues), check open and closed issues first, and use sanitized or synthetic examples. Posting follows the user's existing authorization; without it, the agent prepares a draft. Installing a plugin alone does not authorize public posting.

## Installation

### Codex

Codex users should follow the installation instructions in the dedicated
[`me.codex`](https://github.com/storytellerF/me.codex) repository.

### Claude Code

Claude Code users should follow the installation and migration instructions in the dedicated
[`me.claude`](https://github.com/storytellerF/me.claude) repository.

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for builds, validation, CI, and distribution synchronization.

## Host Emulator Access From a VM

Choose the route and target first. The host ADB server normally uses 5037; an
individual emulator has its own console/ADB port pair, often 5554/5555. Use the
observed endpoint for the selected emulator rather than assuming every device uses 5555.
With gvproxy, the guest host alias `192.168.127.254` reaches host loopback, so check
that existing route before adding a Windows proxy. Other isolated VM networks may
need a scoped proxy/firewall rule. This example specifically assumes the selected
ADB endpoint is 5555, VM subnet is `192.168.80.0/24`, and its host interface is `192.168.80.1`:

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

If it is not listening, inspect the interface address, port owner, proxy entry and
IP Helper service state. Restarting that service interrupts other port proxies;
use an owned maintenance window instead of a blanket stop/start workaround.

The [QEMU Alpine Docker plugin](plugins/qemu-alpine-docker/README.md#vm--containers-status-panel) includes a read-only VM, service-health, and container status panel for MCP Apps hosts.

Android tooling also provides [emulator status and on-demand screen previews](plugins/android-emulator-profile/README.md#android-emulators-status-panel) and a [device lease panel](plugins/android-device-lock/README.md#device-leases-status-panel).
