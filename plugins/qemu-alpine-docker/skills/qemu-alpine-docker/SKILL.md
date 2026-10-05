---
name: qemu-alpine-docker
description: Use when creating, starting, stopping, troubleshooting, or viewing status for a persistent QEMU Alpine Docker VM inside Linux Docker containers or on Windows. Includes KVM, WHPX, and TCG workflows for Docker and Testcontainers; On Linux hosts outside containers, use Docker directly without this plugin; do not trigger for ordinary Docker workflows.
---

# QEMU Alpine Docker

## Current scope

For now, use this plugin for Linux Docker container environments and Windows environments. On Linux hosts running outside containers, use Docker directly without provisioning a QEMU VM through this plugin.

## Design invariants

- Use the bundled persistent Alpine VM with unprivileged user networking inside Linux Docker containers and on Windows.
- Run at most one plugin VM at a time. The scripts serialize lock-state updates with an atomic guard and enforce a global VM lock.
- In auto mode, probe KVM with `-cpu host` on Linux or WHPX with `-cpu qemu64` on Windows. Fall back to multi-threaded TCG with `-cpu max` if hardware acceleration is unavailable. Explicit `kvm`/`whpx` must fail clearly instead of silently falling back.
- Use QEMU user-mode networking with either accelerator.
- Bind every host forward to `127.0.0.1`.
- Reuse the persistent qcow2 disk so Docker images survive between test runs.
- Resolve guest and container DNS through local Unbound. Let the guest use loopback, configure Docker containers to use bridge gateway `172.17.0.1`, and forward upstream only over TCP to QEMU's virtual DNS server at `10.0.2.3`.
- Keep Testcontainers Ryuk enabled.
- Pass the profile's extended Testcontainers pull pause and total timeouts to host test processes because large image extraction can be quiet under TCG fallback.
- Use platform-aware `auto` resource metrics: collect Windows/guest metrics through PowerShell on Windows; run Linux commands without that collector. Preserve test exit codes. Explicit `true` requires the Windows collector.
- Keep Docker's automatic published-port range equal to the QEMU same-port forwarding range.
- Never silently delete an incomplete disk or use `docker image prune -a`.
- Treat TCP port 2375 as a root-equivalent, unauthenticated API; do not expose it beyond loopback.
- Render provisioning configuration from `templates/*.tpl` with the shared `render_template` helper; keep scripts limited to runtime values and orchestration.

## Paths

- `scripts/setup.sh`: prerequisites and verified Alpine ISO download
- `scripts/create-vm.sh`: unattended install and post-boot verification
- `scripts/select-apk-mirror.sh`: first-provisioning mirror detection, HTTPS validation, and official-CDN fallback
- `scripts/start-vm.sh`: background start with automatic or explicitly selected acceleration
- `scripts/stop-vm.sh`: graceful or forced shutdown
- `scripts/run-testcontainers.sh`: host test command using guest Docker
- `scripts/collect-resource-metrics.ps1`: Windows host and Alpine guest resource sampler used by the Testcontainers wrapper
- `scripts/run-docker.sh`: guest Docker CLI over SSH
- `scripts/sync-workspace.sh`: copy a host workspace into the guest over SSH without running project commands
- `scripts/connect-vm.sh`: connect to the guest through an interactive SSH or SFTP session
- `scripts/vm-utils.sh`: stable shared-utility facade and common path initialization
- `scripts/lib/`: focused runtime, configuration, template, QEMU, guest, Alpine-image, and VM-state modules loaded by the facade

- `templates/`: Alpine answers, guest setup, sysctl, and Docker daemon configuration templates
- `templates/unbound.conf.tpl`: guest and Docker bridge DNS service with forced TCP forwarding to QEMU DNS
- `profiles/dev.profile`
- `tests/test-vm-utils.sh`
- `tests/test-apk-mirror-selection.sh`

## Linux containers

Read `container/README.md` at the plugin root for the ordinary, non-root container workflow. KVM can be enabled with `/dev/kvm` device access and the matching supplementary group; do not require `--privileged`. Use TCG if KVM is unavailable. Keep the test process, QEMU, and MCP status server in the same outer container's process/network namespace. Preserve loopback-only Docker and Testcontainers forwards. The guest is x86-64; KVM requires a compatible Linux host CPU.

## Read-only status panel

For requests to view VM state, service health, or containers, call `qemu_docker_status` to open **VM & Containers** in hosts supporting MCP Apps. It has an `openai/ui` thread entrypoint and takes no arguments. Refresh remains within the panel. Never start a VM or provision resources merely to populate this view.

Without MCP Apps support, run `scripts/status.py` with Python 3 and summarize its JSON snapshot. Read `QEMU_STATUS_PROFILE` for a custom profile and `QEMU_ALPINE_BASE_DIR` for existing state overrides; do not invent a running state from the ready marker. Unknown probes, unavailable lists, and stale PID files must be reported as such. SSH health means a banner was received, not successful authentication. Resource counts and accelerator policy are profile configuration, not measured utilization. The separate accelerator field is read from the running process when available.

- `scripts/status.py`: read-only local status collection.
- `scripts/status-server.py`: stdio MCP App server with a thread entrypoint.
- `templates/status-panel.html`: bundled dashboard, rebuilt from `ui/`.

## Workflow

Before a workflow downloads an ISO, provisions a disk, or starts a VM, obtain user approval.

Initial setup:

```bash
./scripts/setup.sh
./scripts/create-vm.sh ./profiles/dev.profile
```

Daily testing:

```bash
./scripts/start-vm.sh ./profiles/dev.profile
./scripts/run-testcontainers.sh -- <test command>
./scripts/stop-vm.sh ./profiles/dev.profile
```

When project files must exist inside the guest, sync them separately and then run the project's own build or test command:

```bash
./scripts/sync-workspace.sh --remote-dir /root/my-project /path/to/project
```

The sync command excludes common generated and private paths by default, accepts repeated `--exclude` options, and never runs a project-specific build.

The start script returns after SSH and the Docker API are ready. The test wrapper sets:

- `DOCKER_HOST=tcp://127.0.0.1:<DOCKER_DAEMON_PORT>`
- `TESTCONTAINERS_HOST_OVERRIDE=127.0.0.1`
- `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock`

It unsets TLS variables and `TESTCONTAINERS_RYUK_DISABLED`, runs the test command, then reports resource averages and peaks without changing the command's exit code.

## Configuration and recovery

Read [`references/configuration-and-recovery.md`](references/configuration-and-recovery.md)
when changing profile values, port forwarding, acceleration, mirrors, image preloading,
resource metrics, bind-mount behavior, or incomplete provisioning recovery.

## Validation

```bash
./tests/test-apk-mirror-selection.sh
./tests/test-vm-utils.sh
./tests/test-sync-workspace.sh
```
