# QEMU Alpine Docker

This plugin creates one persistent Alpine Linux VM for host-side Docker and Testcontainers tests on Windows. It automatically uses QEMU's WHPX hardware acceleration when available and falls back to portable TCG emulation. Networking remains unprivileged QEMU user-mode networking with loopback-only port forwarding.

## Architecture

- Alpine is installed unattended to a persistent qcow2 system disk.
- Automatic acceleration uses `whpx + qemu64` on compatible Windows hosts and `tcg,thread=multi + max` otherwise. Both expose the instructions needed by current x86-64-v2 container images.
- Provisioning configuration is rendered from files under `templates/`; scripts supply explicit placeholder values instead of embedding generated files in heredocs.
- Shared shell behavior is loaded through `scripts/vm-utils.sh`, which initializes common paths and sources focused modules under `scripts/lib/` for runtime, configuration, templating, QEMU, guest access, Alpine images, and VM state.
- During first provisioning, Alpine selects the fastest mirror from its official list, upgrades the result to HTTPS, validates it, and falls back to the official HTTPS CDN when needed.
- Unbound accepts guest DNS queries from loopback and the Docker bridge, then forwards them over TCP to QEMU's virtual DNS server at `10.0.2.3`. Docker containers use the bridge gateway at `172.17.0.1` as their resolver. This avoids unreliable upstream UDP return traffic in Windows user-mode networking without depending on a host DNS listener. DHCP lease renewals are prevented from replacing the local resolver selection.
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
- Windows Hypervisor Platform for WHPX acceleration; the plugin remains usable through TCG when it is unavailable
- `xorriso`
- OpenSSH client and key generator
- `curl`, `tar`, and `sha256sum`

## First-time provisioning

```bash
./scripts/setup.sh
./scripts/create-vm.sh ./profiles/dev.profile
```

`setup.sh` downloads and verifies the official Alpine virt ISO. `create-vm.sh` builds the unattended ISO, selects the configured accelerator, directly boots the kernel for deterministic automation, selects and persists a usable package mirror, configures Unbound as a local DNS-to-TCP forwarder, boots the disk once, verifies DNS, Docker, and the selected repositories, then writes the persistent ready marker. Mirror selection happens only while provisioning a new disk. If a disk exists without the ready marker, the script stops and preserves it for inspection instead of silently rebuilding it.

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

The wrapper passes `DOCKER_HOST`, `TESTCONTAINERS_HOST_OVERRIDE`, and `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE` explicitly across the MSYS-to-Windows process boundary. On Windows it also restores a writable native temporary directory before launching JVM tests. It keeps Ryuk enabled. Random published ports work when the framework asks Docker to assign a port because guest allocation and host forwards share the configured range.

Every wrapped command collects host-wide, QEMU-process, and Alpine-guest CPU and memory metrics by default. Only the final average/peak summary is printed, the original command exit code is preserved, and a structured report atomically replaces `~/.qemu-alpine-docker/metrics/latest.json`. The report intentionally omits the command text and working-directory path. Very short commands can finish before the first sample and therefore produce `null` aggregates.

Other operations:

```bash
./scripts/run-docker.sh -- ps
./scripts/connect-vm.sh               # interactive SSH session
./scripts/connect-vm.sh --sftp        # SFTP session
./scripts/stop-vm.sh ./profiles/dev.profile
```

## Profile settings

- `VM_NAME`, `VM_MEMORY`, `VM_CPUS`, `VM_DISK_SIZE`
- `VM_ACCELERATOR=auto|whpx|tcg`; `auto` prefers WHPX after a capability probe and falls back to TCG
- `SSH_PORT` and `DOCKER_DAEMON_PORT`
- `TESTCONTAINERS_PORT_START` and `TESTCONTAINERS_PORT_END` (maximum 512 ports)
- `TESTCONTAINERS_PULL_PAUSE_TIMEOUT` and `TESTCONTAINERS_PULL_TIMEOUT` in seconds; the bundled profile raises both for large image extraction under TCG fallback
- `TESTCONTAINERS_RESOURCE_METRICS=true|false` and `TESTCONTAINERS_RESOURCE_METRICS_INTERVAL=1`; collection requires Windows PowerShell and accepts intervals from 1 to 60 seconds
- `PORT_FORWARD=host:guest,...` for additional fixed loopback forwards
- `ALPINE_BRANCH` and `ALPINE_MIRROR_BASE`; use `auto` for fastest-mirror detection or an explicit `http://`/`https://` base URL to disable detection
- `PRELOAD_IMAGES=image,...`

The bundled development profile selects acceleration automatically and allocates 4 GiB of guest memory plus four virtual CPUs for multi-container and JVM-based Testcontainers suites.

Fixed host ports must not overlap the Testcontainers range. All forwards bind to `127.0.0.1`.

## Measured resource reference

A Windows host with 28 logical processors and 31.8 GiB RAM ran a cached Elasticsearch 8.17 Testcontainers integration test through the bundled 4-vCPU, 4-GiB profile with automatic resource collection enabled. `VM_ACCELERATOR=auto` selected WHPX. The wrapper recorded a successful 20-second command, Gradle reported 16 seconds, the test case took 14.89 seconds, and Elasticsearch became ready in 10.41 seconds. The collector produced 13 valid samples with no sampling errors. The VM reached SSH and Docker readiness in 26 seconds from a cold VM start. On the same persistent disk, an earlier TCG run needed about 3 minutes 12 seconds for Elasticsearch startup.

| Scope | CPU average | CPU peak | Memory average | Memory peak |
| --- | ---: | ---: | ---: | ---: |
| Windows host, all activity | 23.8% | 35.0% | 29,145 MiB / 89.4% used | 29,279 MiB / 89.8% used |
| QEMU process | 6.5% | 10.2% | 3,464 MiB working set | 3,472 MiB working set |
| Alpine guest | 44.3% | 71.5% | 1,732 MiB used | 2,967 MiB / 75.6% used |

Host and QEMU CPU percentages are normalized across all host logical processors; guest CPU is normalized across its four virtual CPUs. QEMU and guest CPU averages exclude their initial counter baselines. Guest sampling uses SSH, so the figures include that small measurement overhead. Host-wide memory reflects unrelated applications already running on the measurement machine; use the QEMU working set and guest figures when sizing this VM.

## Validation

```bash
./tests/test-apk-mirror-selection.sh
./tests/test-vm-utils.sh
```

The smoke tests use deterministic command mocks; they do not boot QEMU or use the network.
