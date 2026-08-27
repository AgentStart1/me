---
name: qemu-alpine-docker
description: Manages a single persistent pure-TCG QEMU Alpine Docker VM on Windows for Docker API and Testcontainers development or testing, including unattended provisioning, loopback port ranges, image-cache reuse, code sync, and lifecycle operations.
---

# QEMU Alpine Docker

Use this skill for the bundled Alpine VM instead of configuring a Windows bridge, WHPX, or a disposable VM.

## Design invariants

- Run at most one plugin VM at a time. The scripts serialize lock-state updates with an atomic guard and enforce a global VM lock.
- Use pure TCG and QEMU user-mode networking.
- Bind every host forward to `127.0.0.1`.
- Reuse the persistent qcow2 disk so Docker images survive between test runs.
- Keep Testcontainers Ryuk enabled.
- Keep Docker's automatic published-port range equal to the QEMU same-port forwarding range.
- Never silently delete an incomplete disk or use `docker image prune -a`.
- Treat TCP port 2375 as a root-equivalent, unauthenticated API; do not expose it beyond loopback.

## Paths

- `scripts/setup.sh`: prerequisites and verified Alpine ISO download
- `scripts/create-vm.sh`: unattended install and post-boot verification
- `scripts/start-vm.sh`: background pure-TCG start
- `scripts/stop-vm.sh`: graceful or forced shutdown
- `scripts/run-testcontainers.sh`: host test command using guest Docker
- `scripts/run-docker.sh`: guest Docker CLI over SSH
- `scripts/sync-code.sh`: open an interactive SSH or SFTP session to the guest
- `profiles/dev.profile`
- `tests/test-vm-utils.sh`

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

It unsets TLS variables and `TESTCONTAINERS_RYUK_DISABLED`, then replaces itself with the test command.

## Profiles

Profiles are literal `KEY=value` files and must not contain shell expansion. Required network settings are:

- `SSH_PORT`
- `DOCKER_DAEMON_PORT`
- `TESTCONTAINERS_PORT_START`
- `TESTCONTAINERS_PORT_END`

The range may contain at most 512 ports. Additional `PORT_FORWARD=host:guest,...` mappings must not overlap reserved ports.

`PRELOAD_IMAGES` optionally pulls a comma-separated image list during provisioning. Registry paths, tags, digests, dots, dashes, and underscores are accepted. Otherwise, Testcontainers pulls once and Docker reuses the layers from the persistent disk.

## Limitations

Because Docker runs in a remote guest, Windows host paths cannot be used as ordinary Docker bind mounts. Prefer Docker build contexts, named volumes, or test fixtures copied through the Docker API.

If provisioning leaves a disk without a ready marker, inspect the install and verify console logs. When installation is known to be complete and only verification failed, run `VERIFY_EXISTING=true ./scripts/create-vm.sh <profile>` to resume verification. Do not remove the VM directory unless the user explicitly chooses to rebuild it.

## Validation

```bash
./tests/test-vm-utils.sh
```
