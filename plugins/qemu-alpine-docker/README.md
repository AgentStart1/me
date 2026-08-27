# QEMU Alpine Docker

This plugin creates one persistent Alpine Linux VM for host-side Docker and Testcontainers tests on Windows. It deliberately uses pure QEMU TCG, QEMU user-mode networking, and loopback port forwarding—no bridge and no WHPX.

## Architecture

- Alpine is installed unattended to a persistent qcow2 system disk.
- Provisioning configuration is rendered from files under `templates/`; scripts supply explicit placeholder values instead of embedding generated files in heredocs.
- During first provisioning, Alpine selects the fastest mirror from its official list, upgrades the result to HTTPS, validates it, and falls back to the official HTTPS CDN when needed.
- Docker and SSH start automatically in the guest.
- Docker exposes its unauthenticated API only through QEMU's host loopback forward at `127.0.0.1:2375`.
- Docker automatically allocates published ports from `20000–20255`; QEMU forwards every port in that range to the same guest port.
- A global lock permits only one VM from this plugin to run at a time, which also reserves the forwarded range. Lock-state changes are serialized with an atomic guard directory so concurrent launchers cannot overwrite each other.
- Docker images remain on the qcow2 disk and are reused by later test runs. Do not recreate the VM or run `docker image prune -a` if cache reuse matters.
- Testcontainers Ryuk stays enabled and uses the guest Docker socket.

Host bind mounts are not directly available to the remote guest daemon. Use Docker build contexts or named volumes when tests need host files.

## Prerequisites

Run the scripts from Git Bash or MSYS2 with:

- QEMU (`qemu-system-x86_64` and `qemu-img`)
- `xorriso`
- OpenSSH client and key generator
- `curl`, `tar`, and `sha256sum`

## First-time provisioning

```bash
./scripts/setup.sh
./scripts/create-vm.sh ./profiles/dev.profile
```

`setup.sh` downloads and verifies the official Alpine virt ISO. `create-vm.sh` builds the unattended ISO, directly boots its kernel for deterministic automation, selects and persists a usable package mirror, installs through TCG, boots the disk once, verifies Docker and the selected repositories, then writes the persistent ready marker. Mirror selection happens only while provisioning a new disk. If a disk exists without the ready marker, the script stops and preserves it for inspection instead of silently rebuilding it.

When the install log proves that disk installation completed and only post-boot verification failed, resume verification without reinstalling:

```bash
VERIFY_EXISTING=true ./scripts/create-vm.sh ./profiles/dev.profile
```

Set `PRELOAD_IMAGES` in a profile to a comma-separated list if a few images should be pulled during initial verification. Image references may contain registry paths, tags, digests, dots, dashes, and underscores. Normal Testcontainers pulls are cached automatically on the persistent disk.

## Daily use

Start the VM in the background:

```bash
./scripts/start-vm.sh ./profiles/dev.profile
```

Run host tests through the guest Docker API:

```bash
./scripts/run-testcontainers.sh -- npm test
```

The wrapper exports `DOCKER_HOST`, `TESTCONTAINERS_HOST_OVERRIDE`, and `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE` for the child process. It keeps Ryuk enabled. Random published ports work when the framework asks Docker to assign a port because guest allocation and host forwards share the configured range.

Other operations:

```bash
./scripts/run-docker.sh -- ps
./scripts/sync-code.sh                # interactive SSH session
./scripts/sync-code.sh --sftp         # SFTP session
./scripts/stop-vm.sh ./profiles/dev.profile
```

## Profile settings

- `VM_NAME`, `VM_MEMORY`, `VM_CPUS`, `VM_DISK_SIZE`
- `SSH_PORT` and `DOCKER_DAEMON_PORT`
- `TESTCONTAINERS_PORT_START` and `TESTCONTAINERS_PORT_END` (maximum 512 ports)
- `PORT_FORWARD=host:guest,...` for additional fixed loopback forwards
- `ALPINE_BRANCH` and `ALPINE_MIRROR_BASE`; use `auto` for fastest-mirror detection or an explicit `http://`/`https://` base URL to disable detection
- `PRELOAD_IMAGES=image,...`

Fixed host ports must not overlap the Testcontainers range. All forwards bind to `127.0.0.1`.

## Validation

```bash
./tests/test-apk-mirror-selection.sh
./tests/test-vm-utils.sh
```

The smoke tests use deterministic command mocks; they do not boot QEMU or use the network.
