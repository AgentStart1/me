---
name: qemu-alpine-docker
description: Use on Windows when creating, configuring, starting, stopping, or troubleshooting this persistent QEMU Alpine VM for a local Docker API or host-side Testcontainers development and testing. Do not trigger for ordinary Docker, Linux Docker, or Testcontainers workflows that do not use this QEMU VM.
---

# QEMU Alpine Docker

## Design invariants

- Use the bundled persistent Alpine VM instead of configuring a Windows bridge or a disposable VM.
- Run at most one plugin VM at a time. The scripts serialize lock-state updates with an atomic guard and enforce a global VM lock.
- Prefer WHPX hardware acceleration with QEMU's compatible `qemu64` CPU model on Windows, and fall back to multi-threaded TCG with the `max` CPU model when WHPX is unavailable.
- Use QEMU user-mode networking with either accelerator.
- Bind every host forward to `127.0.0.1`.
- Reuse the persistent qcow2 disk so Docker images survive between test runs.
- Resolve guest and container DNS through local Unbound. Let the guest use loopback, configure Docker containers to use bridge gateway `172.17.0.1`, and forward upstream only over TCP to QEMU's virtual DNS server at `10.0.2.3`.
- Keep Testcontainers Ryuk enabled.
- Pass the profile's extended Testcontainers pull pause and total timeouts to host test processes because large image extraction can be quiet under TCG fallback.
- Collect host, QEMU-process, and guest CPU and memory metrics around every Testcontainers command by default. Preserve the command exit code, print only the final summary, and atomically replace the privacy-safe `metrics/latest.json` report.
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
- `scripts/connect-vm.sh`: connect to the guest through an interactive SSH or SFTP session
- `scripts/vm-utils.sh`: stable shared-utility facade and common path initialization
- `scripts/lib/`: focused runtime, configuration, template, QEMU, guest, Alpine-image, and VM-state modules loaded by the facade

- `templates/`: Alpine answers, guest setup, sysctl, and Docker daemon configuration templates
- `templates/unbound.conf.tpl`: guest and Docker bridge DNS service with forced TCP forwarding to QEMU DNS
- `profiles/dev.profile`
- `tests/test-vm-utils.sh`
- `tests/test-apk-mirror-selection.sh`

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
```
