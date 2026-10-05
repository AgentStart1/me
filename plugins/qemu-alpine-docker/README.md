# QEMU Alpine Docker

This plugin creates one persistent Alpine Linux VM for Docker and Testcontainers workflows on Linux, inside ordinary Linux containers, and on Windows. Automatic acceleration probes KVM on Linux or WHPX on Windows, then falls back to portable TCG emulation. Networking remains unprivileged QEMU user-mode networking with loopback-only port forwarding.

## Architecture

- Alpine is installed unattended to a persistent qcow2 system disk.
- Automatic acceleration uses `kvm + host` on Linux with accessible KVM, `whpx + qemu64` on compatible Windows hosts, and `tcg,thread=multi + max` otherwise. KVM requires a compatible x86-64 host CPU; TCG emulates the instruction set on other hosts.
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

To copy a host workspace into the guest before running project-specific commands:

```bash
./scripts/sync-workspace.sh --remote-dir /root/my-project /path/to/project
```

The script sends a tar stream over SSH into a staging directory and replaces the destination only after the transfer succeeds, retaining the prior copy as `<destination>.previous`. It excludes `.git`, `target`, `node_modules`, `dist`, and `.env` by default; pass `--exclude <pattern>` for additional project-specific exclusions. It intentionally does not build or test the project.

## Prerequisites

Run the scripts from Bash on Linux or Git Bash/MSYS2 on Windows with:

- QEMU (`qemu-system-x86_64` and `qemu-img`)
- Optional `/dev/kvm` device access on Linux or Windows Hypervisor Platform on Windows; TCG needs neither
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

The default `auto` metrics mode collects host-wide, QEMU-process, and Alpine-guest CPU and memory metrics on Windows, and runs Linux commands without the PowerShell collector. Only the final average/peak summary is printed, the original command exit code is preserved, and a structured report atomically replaces `~/.qemu-alpine-docker/metrics/latest.json`. The report intentionally omits the command text and working-directory path. Very short commands can finish before the first sample and therefore produce `null` aggregates.

Other operations:

```bash
./scripts/run-docker.sh -- ps
./scripts/sync-workspace.sh --remote-dir /root/my-project /path/to/project
./scripts/connect-vm.sh               # interactive SSH session
./scripts/connect-vm.sh --sftp        # SFTP session
./scripts/stop-vm.sh ./profiles/dev.profile
```

## Profile settings

- `VM_NAME`, `VM_MEMORY`, `VM_CPUS`, `VM_DISK_SIZE`
- `VM_ACCELERATOR=auto|kvm|whpx|tcg`; `auto` probes KVM on Linux or WHPX on Windows before falling back to TCG. Explicit hardware modes fail if unavailable
- `SSH_PORT` and `DOCKER_DAEMON_PORT`
- `TESTCONTAINERS_PORT_START` and `TESTCONTAINERS_PORT_END` (maximum 512 ports)
- `TESTCONTAINERS_PULL_PAUSE_TIMEOUT` and `TESTCONTAINERS_PULL_TIMEOUT` in seconds; the bundled profile raises both for large image extraction under TCG fallback
- `TESTCONTAINERS_RESOURCE_METRICS=auto|true|false` and `TESTCONTAINERS_RESOURCE_METRICS_INTERVAL=1`; collection requires Windows PowerShell and accepts intervals from 1 to 60 seconds
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

## VM & Containers status panel

The plugin includes a read-only MCP App for the conversation panel described in the [OpenAI plugin extensions](https://developers.openai.com/plugins/build/extensions). Open **VM & Containers** from a supporting host's thread tabs, or ask to show the QEMU / Docker status. The `qemu_docker_status` tool returns a snapshot and the bundled UI resource.

The panel shows:

- VM name, verified QEMU process state and PID, disk presence, provisioning marker, actual process accelerator when readable, and profile resource values. CPU/memory and accelerator policy are configured values, not live utilization.
- Local SSH banner reachability and Docker API ping/version. SSH authentication and guest DNS are not tested.
- All running and stopped Docker containers, image, status (including Docker health text), and published ports, with name/image filtering.
- Observation time, probe failures, and warnings when local services respond without a verified QEMU process.

Use **Refresh** for a new snapshot. Optional auto-refresh runs every ten seconds while the panel is visible. An unsuccessful refresh preserves the last snapshot and labels it as stale. An unavailable container list is distinguished from a successfully queried empty list.

### Local MCP runtime

Install [uv](https://docs.astral.sh/uv/) on the Linux/Windows host or inside the Linux container running the VM. The compatibility manifests register `.mcp.json`; the host launches a Python stdio server with pinned dependencies. It must run in the same process and network namespace as QEMU because probes are restricted to `127.0.0.1` and ignore HTTP proxy settings. Opening the panel does not start/stop a VM, provision a disk, install tools, modify state files, or mutate containers. There is no settings extension.

Defaults match `profiles/dev.profile` and `~/.qemu-alpine-docker`. For a custom existing VM, set `QEMU_STATUS_PROFILE` to its profile file and use the existing `QEMU_ALPINE_BASE_DIR` override if necessary. Paths should be native absolute paths for the Python runtime; Git Bash/MSYS paths are converted through `cygpath` on Windows. Profiles are parsed as data and never evaluated as shell code. A different active VM lock produces a profile-selection warning.

```bash
uv run --script scripts/status-server.py
# Plain JSON snapshot, useful in hosts without MCP Apps rendering:
python scripts/status.py
```

The panel uses the official MCP Apps JavaScript SDK and `openai/ui` thread entrypoint. Its HTML contains the entire bundled script with no external UI dependencies or direct browser calls to Docker. Native rendering depends on host support. This package is a local stdio integration; it does not deploy or register a remote ChatGPT service. Hardware acceleration depends on the host; mocked capability tests do not establish hardware availability.

### Build and validate

The checked-in `templates/status-panel.html` is generated from `ui/`. Python and uv are runtime requirements for the MCP server; Node is only needed when rebuilding the UI.

```bash
npm ci --prefix ui
npm run build --prefix ui
npm test --prefix ui
uv run --script tests/test-status.py
# Browser tests against a simulated MCP Apps host:
uv run --script tests/test-status-panel.py
```

The browser test needs Playwright Chromium installed (`uv run --with playwright==1.62.0 playwright install chromium`) or `PLAYWRIGHT_CHROMIUM_EXECUTABLE` pointing to an existing Chromium executable. CI rebuilds the bundle, runs protocol/probe/browser tests, and validates generated Codex packages.

## Linux container workflow

See [container/README.md](container/README.md) for the non-root runtime image, persistent storage, and complete commands. An ordinary container can run QEMU with TCG. On compatible Linux hosts, add `--device=/dev/kvm` and the device's group to enable KVM; neither mode requires `--privileged`, a host Docker socket, or a host-network bridge.

Run the test process and status MCP service in the same outer container as QEMU. Loopback forwards stay inside that network namespace. The guest Docker daemon creates containers using its own Linux kernel; its privileges do not require a privileged outer container. Guest architecture remains x86-64, and KVM requires host/guest architecture compatibility.

## Plugin packaging

`plugin.json` is the portable metadata source. Client manifests and complete skill resources are generated into `me.claude` and `me.codex`; install from those repositories. Source skills use portable frontmatter. Claude routing is stored in `extensions.com.anthropic.claude.skillFrontmatter`, keyed by skill directory, and injected only into generated Claude skills. Codex skill files are copied unchanged.
