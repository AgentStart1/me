# QEMU Alpine Docker

This plugin creates one persistent Alpine Linux VM for host-side Docker and Testcontainers tests on Windows. It deliberately uses pure QEMU TCG, QEMU user-mode networking, and loopback port forwarding—no bridge and no WHPX.

## Architecture

- Alpine is installed unattended to a persistent qcow2 system disk.
- Alpine `main` and `community` use `https://mirrors.aliyun.com/alpine`.
- Docker and SSH start automatically in the guest.
- Docker exposes its unauthenticated API only through QEMU's host loopback forward at `127.0.0.1:2375`.
- Docker automatically allocates published ports from `20000–20255`; QEMU forwards every port in that range to the same guest port.
- A global lock permits only one VM from this plugin to run at a time, which also reserves the forwarded range.
- Docker images remain on the qcow2 disk and are reused by later test runs. Do not recreate the VM or run `docker image prune -a` if cache reuse matters.
- Testcontainers Ryuk stays enabled and uses the guest Docker socket.

Host bind mounts are not directly available to the remote guest daemon. Use `sync-code.sh`, build contexts, or named volumes when tests need host files.

## Prerequisites

Run the scripts from Git Bash or MSYS2 with:

- QEMU (`qemu-system-x86_64` and `qemu-img`)
- `xorriso`
- OpenSSH client and key generator
- `curl`, `tar`, and `sha256sum`
- optional `rsync` (otherwise `scp` is used)

## First-time provisioning

```bash
./scripts/setup.sh
./scripts/create-vm.sh ./profiles/dev.profile
```

`setup.sh` downloads and verifies the official Alpine virt ISO. `create-vm.sh` builds the unattended ISO, directly boots its kernel for deterministic automation, installs through TCG, boots the disk once, verifies Docker and the Aliyun repositories, then writes the persistent ready marker. If a disk exists without that marker, the script stops and preserves it for inspection instead of silently rebuilding it.

When the install log proves that disk installation completed and only post-boot verification failed, resume verification without reinstalling:

```bash
VERIFY_EXISTING=true ./scripts/create-vm.sh ./profiles/dev.profile
```

Set `PRELOAD_IMAGES` in a profile to a comma-separated list if a few images should be pulled during initial verification. Normal Testcontainers pulls are cached automatically on the persistent disk.

## Daily use

Start the VM in the background:

```bash
./scripts/start-vm.sh ./profiles/dev.profile
```

Run host tests through the guest Docker API:

```bash
./scripts/run-testcontainers.sh -- npm test
./scripts/run-testcontainers.sh --profile ./profiles/test.profile -- ./gradlew test
```

The wrapper exports `DOCKER_HOST`, `TESTCONTAINERS_HOST_OVERRIDE`, and `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE` for the child process. It keeps Ryuk enabled. Random published ports work when the framework asks Docker to assign a port because guest allocation and host forwards share the configured range.

Other operations:

```bash
./scripts/run-docker.sh -- ps
./scripts/sync-code.sh -- . /root/project
./scripts/stop-vm.sh ./profiles/dev.profile
```

The dev and test profiles intentionally use the same `VM_NAME`, disk, SSH/API ports, and Testcontainers range. They may vary CPU and memory without losing cached Docker layers.

## Profile settings

- `VM_NAME`, `VM_MEMORY`, `VM_CPUS`, `VM_DISK_SIZE`
- `SSH_PORT` and `DOCKER_DAEMON_PORT`
- `TESTCONTAINERS_PORT_START` and `TESTCONTAINERS_PORT_END` (maximum 512 ports)
- `PORT_FORWARD=host:guest,...` for additional fixed loopback forwards
- `ALPINE_BRANCH` and `ALPINE_MIRROR_BASE`
- `PRELOAD_IMAGES=image,...`
- `SYNC_EXCLUDE=pattern,...`

Fixed host ports must not overlap the Testcontainers range. All forwards bind to `127.0.0.1`.

## Validation

```bash
./tests/test-vm-utils.sh
```

The smoke tests do not boot QEMU or use the network.
