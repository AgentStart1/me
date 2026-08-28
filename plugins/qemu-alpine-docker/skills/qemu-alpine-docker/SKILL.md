---
name: qemu-alpine-docker
description: Manages a single persistent accelerated QEMU Alpine Docker VM on Windows for Docker API and Testcontainers development or testing, including unattended provisioning, loopback port ranges, image-cache reuse, guest access, and lifecycle operations.
---

# QEMU Alpine Docker

Use this skill for the bundled Alpine VM instead of configuring a Windows bridge or a disposable VM.

## Design invariants

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

## Profiles

Profiles are literal `KEY=value` files and must not contain shell expansion. Required network settings are:

- `SSH_PORT`
- `DOCKER_DAEMON_PORT`
- `TESTCONTAINERS_PORT_START`
- `TESTCONTAINERS_PORT_END`

The range may contain at most 512 ports. Additional `PORT_FORWARD=host:guest,...` mappings must not overlap reserved ports.

`VM_ACCELERATOR=auto` probes WHPX on Windows and uses it when available, otherwise selecting TCG. Set `whpx` to require hardware acceleration or `tcg` for portable software emulation. WHPX uses `qemu64`; TCG uses `max` so current x86-64-v2 container images are supported.

`ALPINE_MIRROR_BASE=auto` selects the fastest official-list mirror during first provisioning, requires the automatically selected mirror to work over HTTPS, and falls back to the official HTTPS CDN. Set an explicit HTTP(S) base URL to disable automatic selection.

`PRELOAD_IMAGES` optionally pulls a comma-separated image list during provisioning. Registry paths, tags, digests, dots, dashes, and underscores are accepted. Otherwise, Testcontainers pulls once and Docker reuses the layers from the persistent disk.

`TESTCONTAINERS_RESOURCE_METRICS=true` enables one-second sampling by default. Change the interval with `TESTCONTAINERS_RESOURCE_METRICS_INTERVAL=1` (1-60 seconds), or disable collection when PowerShell is unavailable. The latest JSON report is stored below the VM base directory at `metrics/latest.json`; it records timings and aggregate resource values but not the test command or working-directory path.

## Limitations

Because Docker runs in a remote guest, Windows host paths cannot be used as ordinary Docker bind mounts. Prefer Docker build contexts, named volumes, or test fixtures copied through the Docker API.

If provisioning leaves a disk without a ready marker, inspect the install and verify console logs. When installation is known to be complete and only verification failed, run `VERIFY_EXISTING=true ./scripts/create-vm.sh <profile>` to resume verification. Do not remove the VM directory unless the user explicitly chooses to rebuild it.

## Validation

```bash
./tests/test-apk-mirror-selection.sh
./tests/test-vm-utils.sh
```
