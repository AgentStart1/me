# QEMU Guests

This plugin runs concurrent QEMU work VMs alongside one persistent Alpine Linux Docker backend, inside Linux containers and on Windows. Work guests have independent disks and unattended installation media. Guest Docker commands, API access and container TCP ports are proxied to the shared Alpine backend.

For Docker-only workflows on ordinary Linux hosts, use Docker directly. The work-guest supervisor also runs on Linux hosts with QEMU and Python installed.

## Concurrent work VMs

The plugin was renamed from `qemu-alpine-docker` to `qemu-guests`. Install the new name after the client distributions publish. Existing Alpine disks and keys deliberately stay in `~/.qemu-alpine-docker`; `QEMU_ALPINE_BASE_DIR` remains the backend storage override. No disk is moved or recreated by the rename. The VM & Containers panel shows both the backend and registered work VMs, with live read-only screens for running graphical guests.

| Guest | Unattended provisioning | Requirements |
| --- | --- | --- |
| Ubuntu | Official cloud image with NoCloud seed, SSH and Docker proxy bootstrap | Verified amd64 cloud-init qcow2 image |
| Windows | Bundled Autounattend.xml and PowerShell bootstrap | English amd64 BIOS-compatible ISO, matching image edition and available Windows OpenSSH optional features |
| macOS | Recovery terminal automation, `startosinstall`, first-boot product package and launchd Docker tunnel | Prepared English Intel macOS installer ISO, matching firmware/OpenCore hardware, Tesseract on the host and a bootstrap product package built on macOS |
| Other | Custom seed and QEMU installation arguments | OS-specific unattended installer and bootstrap |

The Windows template uses BIOS/MBR with IDE storage and an e1000 NIC. It targets compatible Windows 10/Server media; stock Windows 11 TPM/UEFI and arm64 installers are not bundled. Use a custom adapter for other firmware, drivers or installer requirements. The built-in macOS flow targets Intel Recovery installers with `startosinstall --volume --installpackage`; Apple Silicon IPSW restoration is a separate workflow.

The Windows sample defaults to four vCPUs and `qemu_runtime: "whpx-reset"`. On Windows 11 x64, `install` and `run` build or verify the plugin-managed QEMU 11.1.2 runtime before starting the guest. This runtime contains WHPX only and uses `Westmere,-vmx,-svm`; build or accelerator failures stop the operation without falling back to TCG. Installation uses guest warm reboots in the same QEMU process. `plan`, `status` and `stop` never trigger a build. Ubuntu's sample also selects WHPX explicitly; on Linux select `qemu_runtime: "system"` and KVM.

Install MSYS2 UCRT64 and Python 3.12+ for the managed build. The builder discovers MSYS2 at `~/msys2` or `C:/msys64`; set the host control `QEMU_MSYS2_ROOT` for another installation. The first build installs the required MSYS2 compiler packages, downloads and checks pinned source, applies the bundled patch, and packages the executable, dependent DLLs and firmware under `~/.cache/me/qemu-whpx/<version-recipe>/runtime`. It never overwrites system QEMU. Existing QEMU image tools (`qemu-img`) remain required for disk creation. Source, logs and failed build workspaces remain in the cache for inspection. After an interrupted build, inspect `build.lock` and remaining compiler processes before removing that lock.

To prepare the runtime ahead of guest installation:

```powershell
python scripts/whpx_runtime.py
```

The normal Windows profile needs no executable path or extra DLL PATH setup. Its complete runtime is selected automatically and every cached file is verified before launch. An explicit `qemu` path keeps existing profiles on the system/custom runtime; use `qemu_runtime: "system"` to opt out of management. Do not combine `whpx-reset` with a `qemu` override or an installer cold-boot budget.

Four-vCPU cold startup succeeded with QEMU 11.1.2 and `qemu_args: ["-accel", "whpx", "-cpu", "Westmere,-vmx,-svm"]`. The unmodified executable still failed guest-initiated warm reboot with `Unexpected VP exit code 4`. Switching to Q35, UEFI or masking x2APIC did not resolve the tested failure. Upgrading QEMU alone does not establish compatibility.

The bundled [WHPX partition-reset patch](patches/qemu-11.1.2-whpx-partition-reset.patch) adapts an [upstream proposal](https://patchew.org/QEMU/20260421205749.55060-1-mohamed@unpredictable.fr/) and is not part of the stock release. Four-vCPU Windows Server 2025 warm reboots and guest Docker CLI/API passed on Windows 11. See [build and verification instructions](DEVELOPMENT.md#whpx-four-vcpu-windows-reboots). The reset API requires Windows 11 on x64; Windows 10 and patched UEFI installations are not validated.

Public reports match these symptoms: [QEMU #2042](https://gitlab.com/qemu-project/qemu/-/issues/2042) describes four-vCPU WHPX reboot failures, and [#2402](https://gitlab.com/qemu-project/qemu/-/issues/2402) describes Windows/UEFI reboot hangs. The [qemu-virgl-whpx project](https://github.com/Tsuki-Bakery/qemu-virgl-whpx#Windows-guests) provides Windows guest launch examples but also lists reboot failure as a limitation. Linux KVM configurations such as [dockur/windows](https://github.com/dockur/windows) are useful installation references, not evidence of a WHPX reboot fix.

For legacy system-runtime profiles only, `install_reboots: 4` explicitly allows up to four cold boots during Windows installation. QEMU exits instead of resetting internally; after a clean pre-acceptance exit, the supervisor starts it again with the same disk, seed and accelerator, selecting the disk before installer media. Crashes, stop requests, exhausted budgets and the original readiness deadline stop this flow. Acceptance waits for the bootstrap's final reboot. The managed runtime rejects this option because it supports warm reboot directly.

Each work VM has its own `state_dir`, qcow2 disk, supervisor lease and host SSH port. Multiple work VMs can run simultaneously. Assign different host SSH ports and keep them disjoint from Alpine's host forwards. Work guests share the backend's containers, images and volumes; choose project/container/volume names accordingly.

### Provision and run

1. Provision/start the Alpine backend using the existing commands below. Keep it running while work guests use Docker.
2. Install media authoring support: `python -m pip install -r scripts/requirements-guests.txt`.
3. Generate a guest access key: `ssh-keygen -t ed25519 -f ~/.ssh/qemu-work`. This authenticates host access to work guests; a separate backend key authenticates guest Docker access to Alpine.
4. Build a native proxy for each guest OS. Compilation runs inside Alpine:

   ```bash
   ./scripts/build-docker-proxy.sh --target-os linux --target-arch amd64
   ./scripts/build-docker-proxy.sh --target-os windows --target-arch amd64
   ./scripts/build-docker-proxy.sh --target-os darwin --target-arch amd64
   ```

   Explicit targets use `<proxy-dir>/<os>-<arch>/`, preserving the host executable. `--profile` selects a non-default Alpine profile.
5. Copy `profiles/ubuntu.json` or `profiles/windows.json` outside the plugin checkout. Supply local vendor media, its independently verified SHA-256, keys, proxy binary and backend settings. Paths resolve relative to the JSON profile; `~` expands to the host home. Set the exact Windows image edition. Windows generates a random account password in the private seed.
6. Inspect the plan and install in a dedicated terminal:

   ```bash
   python scripts/guest-vm.py plan /path/to/ubuntu.json
   python scripts/guest-vm.py install /path/to/ubuntu.json
   ```

   Installation is unattended and supervised in the foreground. `Guest ready` means acceptance succeeded: SSH plus Docker server access, and cloud-init completion on Ubuntu. The supervisor stays running throughout the guest's lifetime. Start another guest in another terminal. Logs live in `state_dir`.
7. From another terminal, inspect or stop an individual VM; restart it later with `run`:

   ```bash
   python scripts/guest-vm.py status /path/to/ubuntu.json
   python scripts/guest-vm.py stop /path/to/ubuntu.json
   python scripts/guest-vm.py run /path/to/ubuntu.json
   ```

   Stop requests ACPI shutdown; the supervising terminal reports completion. `stop --force` terminates only that session's verified native QEMU. Ctrl+C cancels the supervisor and forcibly stops its owned QEMU. Stop work guests before the Alpine backend. If a supervisor was killed, inspect the recorded native process before removing retained locks or process records.

Guest terminals receive the proxy on PATH, `DOCKER_HOST=tcp://127.0.0.1:2375` and Testcontainers loopback settings. Ubuntu may need a fresh login shell after bootstrap. Each guest uses its private QEMU user network; `10.0.2.2` reaches the host. SSH tunnels connect to Alpine through the host's existing loopback SSH forward. They bind the API and matching publish-pool ports only to that work guest's `127.0.0.1`. Use identical backend pool bounds in all guest profiles.

Docker CLI builds transfer filtered contexts over SSH. Bind mounts and Testcontainers bind paths refer to Alpine, not the work VM; existing proxy restrictions for `docker cp`, build secrets and unsupported outputs still apply. Published container ports must stay in the pool. Windows guests use Alpine Linux containers, not a Windows container daemon. Large forwarding pools are subject to SSH command-line and descriptor limits.

The Windows proxy uses an in-process SSH transport for command input/output; it does not nest a system SSH process for Docker commands. This avoids stdin/output stalls when invoked from a Windows SSH session. Persistent API/port tunnels still use the Windows OpenSSH service tooling. Proxy compilation uses Go 1.26 or later inside Alpine.

Seeds contain a backend root SSH key and generated Windows credentials. Keep state directories private, outside repositories and shared folders, including on Windows. Never publish seeds, answer files or payload archives. Installation refuses to replace existing disks/seeds. Resume an interrupted install with `run`; media stays attached until acceptance succeeds. Accepted guests boot without installation media.

### Graphical systems and live screens

Set `graphical` to a JSON boolean. Ubuntu defaults to `false`; Windows and macOS default to `true`. A graphical guest requires a unique host `qmp_port`, separate from SSH, backend and other guests' ports. QMP binds only to `127.0.0.1`. The panel does not expose the monitor or accept keyboard/mouse input.

```json
"graphical": true,
"qmp_port": 2241
```

Ubuntu installs XFCE, Xorg and LightDM when graphical; a headless Ubuntu guest omits them. Accounts use SSH keys; set a desktop login password through your authenticated guest administration session if needed. Windows images are selected using the install WIM/ESD metadata: `graphical` chooses the matching Windows Server desktop or Core variant. Use an edition name from your media; naming conventions differ between releases. Windows client editions do not have a Server Core variant. macOS retains its native graphical OS components even in headless operation; `graphical: false` disables panel screen sharing, while Recovery automation still uses its private QMP connection.

Starting/installing a VM registers its public status metadata in `~/.qemu-guests/registry`. Stopped VMs remain listed. The panel distinguishes booting, ready, stopping, stopped, unknown and recovery-required states; an orphaned process is not reported ready. Choose **View screen** to switch between graphical guests. Frames refresh about every two seconds while visible. A failed capture retains the previous frame with an explicit error; screenshots are not included in ordinary status snapshots. Runtime capture files are temporary and deleted after every request. The screen tool accepts only a registered guest ID and verifies process identity and ownership of its loopback QMP listener.

### Unattended Intel macOS installation

1. Prepare a full English Intel-compatible installer application on a macOS preparation machine. Run `scripts/create-macos-media.sh /path/to/Install-macOS.app /absolute/installer.iso`; it uses Apple tools and a newly created dedicated disk image. Record and verify the resulting media checksum.
2. Complete `profiles/macos-adapter.json` with compatible private firmware/OpenCore configuration, the actual installer app path under `/Volumes/`, an explicit empty guest target disk, target proxy, keys, media checksum, and the host Tesseract executable. Supply USB keyboard support in `hardware_args`. Firmware settings belong to your boot configuration, not the panel.
3. Export the private first-boot payload with `python scripts/prepare-macos-payload.py /path/to/macos.json /private/payload.zip`. On the preparation Mac, build `scripts/build-macos-bootstrap.sh /private/payload.zip /private/bootstrap.pkg`. Copy that product package to the profile's `macos.bootstrap_package` path. Keep both files private; they contain the backend key and a generated account password.
4. Run `guest-vm.py install` as for other guests. The controller waits for Recovery using bounded OCR, opens its Terminal with a keyboard shortcut, and hands off to the attached seed's fixed install script. That script refuses a partitioned target, formats only the explicitly configured empty guest disk, and runs `startosinstall` with the bootstrap product package. It never clicks through Setup Assistant or silently retries a destructive handoff after a crash.
5. The installed package supplies a first-boot LaunchDaemon that creates the guest account, enables SSH, installs the Docker tunnel/environment, completes initial setup and reboots. Final acceptance requires authenticated SSH, the Docker CLI and loopback Docker API. A completed OCR/key handoff alone does not establish installation success.

Preparation requires Apple tools (`createinstallmedia`, `pkgbuild`, `productbuild`, `hdiutil`). The Windows/Linux runtime can consume the resulting ISO/package but cannot build them with substitute tools. Installer versions, firmware and boot layouts must match; retain incomplete disks and inspect `macos-install.json` after an interrupted handoff. Do not erase a partially installed guest automatically. The bundled rendering/control tests do not replace installation testing with your selected macOS release.

### Custom unattended adapters

`os: custom` accepts a supplied unattended installer for other systems. macOS now has the built-in flow above.

- `seed_dir` contains flat automation files. The tool adds `payload.zip` with the target proxy, backend key and systemd/launchd or Windows bootstrap. Custom automation must install the payload, configure guest access and run the bootstrap. macOS must source `/opt/qemu-guests/environment` from login-shell configuration. Other OS families provide their own bootstrap.
- `hardware_args` optionally replaces default disk/NIC arguments; placeholders are `{disk}`, `{state}` and `{ssh_port}`. Provide loopback SSH forwarding and preserve the user-network gateway or adapt the bootstrap. Defaults are x86-64 IDE/e1000.
- `qemu_args` applies on every boot, including acceleration and firmware. Managed Windows and the bundled Ubuntu sample select WHPX explicitly; use the system runtime with explicit KVM on Linux. Custom system-runtime profiles must name their accelerator rather than assume QEMU's default is hardware accelerated. Automatic acceleration probing remains a backend feature. Keep monitor/stdin and lifecycle under supervisor ownership.
- `install_args` applies before first acceptance and supports `{state}` and `{seed}`. It must boot automation that consumes the seed unattended. Generic media attachments use IDE CD-ROM; adapters must supply compatible controllers.
- `acceptance` is an optional host argument array, without implicit shell expansion, supporting `{state}` and `{ssh_port}`; it is required for custom guests. Return zero only after installation, access, Docker proxy/API and required port forwards work. Probes are repeatable, read-only and bounded to 15 seconds. Never use a successful no-op as installation acceptance.
- `timeout` bounds readiness in seconds (default 3600). Failures retain the installation disk/seed. OS/media changes require a new state directory. `media_sha256` is checked before disk creation.

See the vendor formats: [Ubuntu NoCloud](https://canonical-cloud-init.readthedocs-hosted.com/en/latest/reference/datasources/nocloud.html), [Windows unattended installation](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/automate-windows-setup). Apple's [Virtualization framework installer](https://developer.apple.com/documentation/virtualization/installing-macos-on-a-virtual-machine) is a separate platform flow, not a QEMU installer bundled here.

## Alpine Docker backend architecture

- Alpine is installed unattended to a persistent qcow2 system disk.
- Automatic acceleration uses `kvm + host` on Linux with accessible KVM, `whpx + qemu64` on compatible Windows hosts, and `tcg,thread=multi + max` otherwise. KVM requires a compatible x86-64 host CPU; TCG emulates the instruction set on other hosts.
- Provisioning configuration is rendered from files under `templates/`; scripts supply explicit placeholder values instead of embedding generated files in heredocs.
- Shared shell behavior is loaded through `scripts/vm-utils.sh`, which initializes common paths and sources focused modules under `scripts/lib/` for runtime, configuration, templating, QEMU, guest access, Alpine images, and VM state.
- During first provisioning, Alpine selects the fastest mirror from its official list, upgrades the result to HTTPS, validates it, and falls back to the official HTTPS CDN when needed.
- Alpine DHCP and Docker containers use gvproxy DNS at `192.168.127.1`. Both UDP and TCP DNS are supported; no guest DNS proxy is installed.
- Docker and SSH start automatically in the guest.
- Docker exposes its unauthenticated API only through gvproxy's host loopback forward at `127.0.0.1:2375`.
- Docker automatically allocates published ports from `20000–20127` on both platforms; gvproxy forwards every TCP port in the selected range to the same guest port before QEMU starts.
- A backend lock permits one Alpine backend at a time and reserves its forwarded range. Work VMs have independent locks and can run concurrently. Backend lock-state changes use an atomic guard so launchers cannot overwrite each other.
- A separate operation lease spans setup, provisioning, start/stop and client commands (tests, Docker, SSH/SFTP, workspace sync and proxy builds). Competing operations fail before changing VM state. Normal exits and handled signals release the lease; after a forced kill, inspect all plugin processes before manually removing an interrupted `run/vm-operation.lock` or `vm-state.guard`.
- QEMU and gvproxy ownership records verify the native executable and creation time before termination. An already-running VM is accepted only after its forwarding rules and guest readiness match the profile. Windows provisioning and legacy shell PID translation use the launching Bash runtime's tools; normal starts retain native PIDs directly.
- Docker images remain on the qcow2 disk and are reused by later test runs. Do not recreate the VM or run `docker image prune -a` if cache reuse matters.
- Testcontainers Ryuk stays enabled and uses the guest Docker socket.

Host bind mounts are not directly available to the remote guest daemon. Use Docker build contexts or named volumes when tests need host files.

### Docker commands from Windows or the outer Linux container over SSH

For Gradle or other test commands that invoke the Docker CLI, compile the native proxy in the environment where the test process runs: Windows or the outer Linux container.

```bash
./scripts/build-docker-proxy.sh
./scripts/run-testcontainers.sh -- ./gradlew test
```

Start the VM before compiling. The script sends the proxy source over existing SSH,
installs Go in Alpine if needed, tests it there, and builds with `CGO_ENABLED=0` for
Windows amd64 or Linux amd64/arm64, according to the environment running the script.
It downloads the executable over SSH; no Go installation is needed on Windows or in the outer container.
Go and its caches stay in the persistent guest; temporary build files are cleaned up.
Use `--profile <path>` for a non-default VM profile.
The wrapper puts the proxy on PATH, so `docker build` filters the local context using Docker's
upstream ignore matcher and sends a tar archive over SSH to guest `docker buildx build --load`.
Dockerfile-specific ignore files override the context's `.dockerignore`. Project Gradle tasks
remain responsible for preparing distributions, selecting targets and naming images.
Other commands run in the guest without copying host files; host bind mounts and `docker cp`
are not translated. Named contexts, build secrets and SSH mounts are rejected until explicit
transport support exists. No unfiltered workspace transfer is performed.

The compiled helper is shared by all projects at `~/.local/share/me/docker-proxy/docker.exe`
on Windows, or `~/.local/share/me/docker-proxy/docker` inside the outer Linux container.
On Windows, `~` resolves to the Windows user profile; in a Linux container, it is the
container user's home directory. Persist that directory or rebuild the helper when replacing the outer container.
Use the same `QEMU_DOCKER_PROXY_DIR` override for compilation and test execution if necessary.

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
- A running Alpine VM with repository access for the first Go installation and dependency download

On Windows, known MSYS2 tool directories and Windows OpenSSH are appended to
`PATH` as fallbacks. Existing commands retain priority, including the Bash runtime
used to launch the scripts. This also makes MSYS2's `xorriso` available without
replacing Git Bash's tools.

## First-time provisioning

```bash
./scripts/setup.sh
./scripts/create-vm.sh ./profiles/dev.profile
```

`setup.sh` downloads and verifies the official Alpine virt ISO. `create-vm.sh` builds the unattended ISO, selects the configured accelerator, directly boots the kernel for deterministic automation, selects and persists a usable package mirror, configures Docker to use gvproxy DNS, boots the disk once, verifies DNS, Docker, and the selected repositories, then writes the persistent ready marker. Mirror selection happens only while provisioning a new disk. If a disk exists without the ready marker, the script stops and preserves it for inspection instead of silently rebuilding it.

When the install log proves that disk installation completed and only post-boot verification failed, resume verification without reinstalling:

Set `VERIFY_EXISTING=true` in a recovery profile, then run:

```bash
./scripts/create-vm.sh /absolute/path/to/recovery.profile
```

Set `PRELOAD_IMAGES` in a profile to a comma-separated list if a few images should be pulled during initial verification. Image references may contain registry paths, tags, digests, dots, dashes, and underscores. Normal Testcontainers pulls are cached automatically on the persistent disk.

## Daily use

Start the VM in the background:

```bash
./scripts/start-vm.sh ./profiles/dev.profile
```

Run host tests through the guest Docker API:

```bash
./scripts/build-docker-proxy.sh # once, and after proxy source updates
./scripts/run-testcontainers.sh -- npm test
```

The wrapper supplies `DOCKER_HOST`, `TESTCONTAINERS_HOST_OVERRIDE`, and `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE` to the test process on both platforms. On Windows it passes them across the MSYS-to-Windows process boundary and restores a writable native temporary directory before launching JVM tests. In a Linux container, the test process runs in the same outer container as QEMU. It keeps Ryuk enabled. Random published ports work when the framework asks Docker to assign a port because guest allocation and host forwards share the configured range.

The default `auto` metrics mode collects host-wide, QEMU-process, and Alpine-guest CPU and memory metrics on Windows, and runs Linux commands without the PowerShell collector. When Windows collection is enabled, only the final average/peak summary is printed and a structured report atomically replaces `~/.qemu-guests/metrics/latest.json`. Linux runs do not produce a metrics summary or update that report. Both platforms preserve the original command exit code. The report intentionally omits the command text and working-directory path. Very short commands can finish before the first sample and therefore produce `null` aggregates.

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
- `TESTCONTAINERS_PORT_START=20000` and `TESTCONTAINERS_PORT_END=auto` (20127 on both platforms); explicit numeric ranges have no port-count ceiling

- `TESTCONTAINERS_PULL_PAUSE_TIMEOUT` and `TESTCONTAINERS_PULL_TIMEOUT` in seconds; the bundled profile raises both for large image extraction under TCG fallback
- `TESTCONTAINERS_RESOURCE_METRICS=auto|true|false` and `TESTCONTAINERS_RESOURCE_METRICS_INTERVAL=1`; collection requires Windows PowerShell and accepts intervals from 1 to 60 seconds
- `PORT_FORWARD=host:guest,...` for additional fixed loopback forwards
- `ALPINE_BRANCH` and `ALPINE_MIRROR_BASE`; use `auto` for fastest-mirror detection or an explicit `http://`/`https://` base URL to disable detection
- `PRELOAD_IMAGES=image,...`

`auto` computes the end from the configured start plus 127, so a custom start
still gets 128 ports. A pool extending above 65535 must use explicit valid bounds.

The bundled development profile selects acceleration automatically and allocates 4 GiB of guest memory plus four virtual CPUs for multi-container and JVM-based Testcontainers suites.

Fixed host ports must not overlap the Testcontainers range. All forwards bind to `127.0.0.1`.

gvproxy owns forwarded listeners, while QEMU owns one TCP transport connection.
The former Windows QEMU listener warning no longer applies to this backend.
The 128-port default is a configurable allocation pool, not a gvproxy capacity
limit. Explicit pools must lie within `1024–65535`, leave guest outbound ports,
and avoid host forwards/control ports and guest Docker API port 2375. Startup
registers the entire pool in one controller using a persistent HTTP connection;
a failed bind or request aborts and cleans the owned helper, without connection retries.
On Linux the helper inherits enough file descriptors for its listeners plus 256
descriptors of connection headroom. A smaller hard limit requires raising the
host/container `nofile` limit or selecting a smaller pool. Host port availability,
memory, descriptors and concurrent connections still determine practical capacity.
Ryuk stays enabled and shares the pool. All plugin forwards currently use TCP;
UDP/SCTP published ports are not exposed by these scripts. Binding listeners
does not prove application responses or load capacity.

New guests use a Docker startup wrapper that sets the selected pool before each
daemon execution, initializes the cached allocator, then restores the outbound kernel
range to `32768–60999` (or its larger disjoint portion for overlapping custom pools).
If a pool covers that whole interval, it selects the larger disjoint portion of
`1024–65535`; a pool leaving no outbound port is rejected before launch.
On fresh guests, a temporary BusyBox image is imported from guest files, published
once to verify allocation, and removed without a registry pull. Restored published
containers also initialize the allocator, allowing a fully occupied pool to restart.
Startup waits for allocator initialization and outbound restoration before reporting
success; guests lacking the wrapper fail with a maintenance instruction. Docker caches its publish range on first use; leaving the publish range
as the outbound range would make guest outbound connections compete for it.
Daemon failures retain their exit status and OpenRC supervision remains enabled.

Existing persistent guests are not automatically migrated. Keep their explicit
profile range until you can update the guest safely. Changing only the host profile
does not change Docker's cached range; startup rejects a persisted pool mismatch.
During a planned maintenance window, update `/etc/sysctl.d/99-testcontainers-ports.conf`
and install the newly rendered wrapper and `/etc/conf.d/docker` configuration with
the same numeric pool, then restart Docker and QEMU. Preserve custom Docker service
settings when updating that configuration. Restarting Docker interrupts containers;
confirm ownership before doing so. A running VM is never restarted to apply defaults.

## Measured resource reference

On Windows, the proxy follows Docker's Windows archive permissions: it adds execute bits and removes
group/world write permissions so scripts can run in Linux images without Dockerfile workarounds.
In a Linux container, it preserves the source file permission bits; scripts must already have their required execute bits.

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

- VM name, verified QEMU process state and PID, disk presence, provisioning marker, actual process accelerator when readable, and configured profile CPU/memory limits.
- Live CPU and memory usage for the QEMU host system, verified QEMU process, and Alpine guest. Host/QEMU CPU percentages use all host logical CPUs; guest CPU uses all guest CPUs. QEMU memory is resident memory relative to host RAM. In an outer Linux container, host system figures come from the kernel's system view, not the outer container's cgroup quota.
- Local SSH banner reachability and Docker API ping/version. SSH authentication and guest DNS are not tested.
- All running and stopped Docker containers, image, status (including Docker health text), and published ports, with name/image filtering. Running containers include CPU and memory usage; container CPU uses 100% per core and can exceed 100%. Memory subtracts inactive file cache where available and shows usage against the Docker-reported limit.
- Observation time, probe failures, and warnings when local services respond without a verified QEMU process.

Use **Refresh** for a new snapshot. Optional auto-refresh runs every ten seconds while the panel is visible. An unsuccessful refresh preserves the last snapshot and labels it as stale. An unavailable container list is distinguished from a successfully queried empty list.

Resource samples are collected on refresh and are independent of the test wrapper's Windows metrics reports. Guest sampling reads `/proc/stat` and `/proc/meminfo` over loopback SSH using the existing VM key; it does not install tools, create keys, or write state. Local host/process sampling uses the pinned psutil dependency in the MCP runtime. Plain Python use of `scripts/status.py` needs psutil for those two scopes. Missing permissions, SSH failures, stopped processes, or missing CPU baselines show unavailable values rather than zero. A failed container sample does not hide the container list. To bound refresh work, each snapshot samples at most 32 running containers, with eight concurrent probes; remaining containers are marked unavailable.

### Local MCP runtime

Install [uv](https://docs.astral.sh/uv/) on the Linux/Windows host or inside the Linux container running the VM. The compatibility manifests register `.mcp.json`; the host launches a Python stdio server with pinned dependencies. It must run in the same process and network namespace as QEMU because probes are restricted to `127.0.0.1` and ignore HTTP proxy settings. Opening the panel does not start/stop a VM, provision a disk, install tools, modify state files, or mutate containers. There is no settings extension.

Defaults match `profiles/dev.profile` and `~/.qemu-guests`. For a custom existing VM, set `QEMU_STATUS_PROFILE` to its profile file and use the existing `QEMU_ALPINE_BASE_DIR` override if necessary. Paths should be native absolute paths for the Python runtime; Git Bash/MSYS paths are converted through `cygpath` on Windows. Profiles are parsed as data and never evaluated as shell code. A different active VM lock produces a profile-selection warning.

```bash
uv run --script scripts/status-server.py
# Plain JSON snapshot, useful in hosts without MCP Apps rendering:
python scripts/status.py
```

The panel uses the official MCP Apps JavaScript SDK and `openai/ui` global sidebar and thread entrypoints. Its HTML contains the entire bundled script with no external UI dependencies or direct browser calls to Docker. Native rendering depends on host support. This package is a local stdio integration; it does not deploy or register a remote ChatGPT service. Hardware acceleration depends on the host; mocked capability tests do not establish hardware availability.

### Build and validate

See [DEVELOPMENT.md](DEVELOPMENT.md) for resource collector behavior and focused panel verification.

The checked-in `templates/status-panel.html` is generated from `ui/`. Python and uv are runtime requirements for the MCP server; Node is only needed when rebuilding the UI.

UI builds support native Windows paths. Windows status probes translate Git Bash/MSYS PIDs to native Windows PIDs before verifying QEMU identity and reading the accelerator. Missing processes report stopped; unavailable inspection tools report unknown.

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

The runtime image normalizes shell, profile, and template line endings so Windows CRLF checkouts can be built and run in Linux containers.

Run the test process and status MCP service in the same outer container as QEMU. Loopback forwards stay inside that network namespace. The guest Docker daemon creates containers using its own Linux kernel; its privileges do not require a privileged outer container. Guest architecture remains x86-64, and KVM requires host/guest architecture compatibility.

## Plugin packaging

`plugin.json` is the portable metadata source. Client manifests and complete skill resources are generated into `me.claude` and `me.codex`; install from those repositories. Source skills use portable frontmatter. Claude routing is stored in `extensions.com.anthropic.claude.skillFrontmatter`, keyed by skill directory, and injected only into generated Claude skills. Codex skill files are copied unchanged.

Docker build options may precede or follow the context directory. Explicit `-f`/`--file`
paths resolve from the host working directory and must stay inside the context.
`--iidfile` writes the image ID back to the requested host path after a successful build.
Relative output paths resolve from the host working directory; their parent directory must exist.
The guest uses a private temporary file and cleans it after transfer or build failure.
`--metadata-file` and `--output`/`-o` remain unsupported and are rejected.

All `build-docker-proxy.sh` invocations share one user-wide lock at
`~/.cache/me/locks/build-docker-proxy.lock`, independent of VM, project, plugin checkout,
and output directory. They wait before upload,
compiler installation, compilation, download, or executable replacement.
`QEMU_DOCKER_BUILD_LOCK_TIMEOUT` sets the wait timeout in seconds (default 900).
Normal exits and handled signals release the owned lock. After a forced kill, a stale lock
produces an error: confirm no compiler or transfer remains before removing the reported
lock directory. Do not remove another running build's lock.

## Network recovery

Use the updated plugin or a matching source checkout for setup, start and stop commands. Until the distribution workflow publishes the update and a new Codex chat loads it, manage the VM with the matching source scripts.

`GVPROXY_QEMU_PORT=19200` and `GVPROXY_API_PORT=19201` are loopback control ports; they must be distinct and outside every forward. Python 3 is required for verified process ownership. `GVPROXY_BINARY` can point to a verified helper installed by `setup.sh`.

If gvproxy exits, stop the VM and start it again. Upstream v0.9.0 accepts one QEMU connection per process, so recovery restarts both processes, re-registers all forwards, and waits for SSH and Docker application responses. It does not reconnect an already-running QEMU automatically. Port conflicts fail startup and remove owned processes. Do not restart a VM used by another session. The API can expose ports and must remain on loopback.

## Improvement feedback

Plugin findings go to [storytellerF/me issues](https://github.com/storytellerF/me/issues). Skills require checking open and closed issues before reporting, using sanitized or synthetic examples, and honoring the user's authorization before posting. Existing reports are reused; unavailable access leaves an unsubmitted draft.

## Python lifecycle and state controller

Use Python 3.10+ to run `scripts/start-vm.py` or `scripts/stop-vm.py` with the same
optional profile argument. The `.sh` commands select an interpreter and retain
the launching Bash runtime through `QEMU_BASH_BINARY`; native callers may set
that variable explicitly. Set `QEMU_STATE_PYTHON` for an explicit interpreter.
Start/stop own readiness, cancellation and failure cleanup in Python. Process
signalling still verifies native executable and creation time through the
shared process identity implementation. The platform/guest adapter plans acceleration
and networking and runs SSH commands without owning lifecycle locks. Python owns
native helper controller subprocesses through cancellation and exit.

`BOOT_TIMEOUT` (SSH readiness, default 300 seconds), `FORCE` (`true` skips graceful
shutdown, default `false`) and `TIMEOUT` (graceful shutdown, default 30 seconds)
are read only from the profile; inherited environment variables do not set them.

Provisioning remains shell orchestration in `create-vm.sh`, using the same Python
state controller for operation leases, global reservations, process registration
and state cleanup. Guest templates and simple command forwarding remain shell.
Unknown process probes, interrupted guards and failed cleanup retain ownership
for inspection. On Windows use Ctrl+C or native Ctrl+Break for graceful
cancellation; Git Bash `kill -TERM` forcibly terminates native Python and cannot
run cleanup. Inspect any remaining operation lease before manual recovery.
After partial PID publication, an owned stop also checks the pending launch PID
and native identity before touching networking or releasing the reservation.
If PID publication is incomplete or identity remains unknown, inspect the retained
state and processes before manual recovery; missing PID files alone do not prove exit.

Failures before QEMU creation, such as an unwritable log or a definite process
creation failure, clean up this launch's helper and reservation automatically.
Initial guard metadata failures also roll back a guard created by that operation,
allowing a retry; pre-existing interrupted guards still require inspection.
Shell clients also retain cleanup responsibility while requesting their lease or
guard. Cancellation waits for the creator to finish, then releases only that
request's resources; failed token delivery can be retried without manual lock removal.
Cancelling helper creation waits for its owned process to exit before removing
its reservation. If exit cannot be confirmed, its recovery evidence remains.
Cancellation before readiness follows the same cleanup when process ownership can
be verified. Once readiness is committed, the VM remains running in the background.
Cancelling a stop preserves remaining ownership so a later stop can finish.
If a native helper controller cannot be confirmed exited, the operation lease
also stays in place; inspect all remaining plugin processes before recovery.
Existing helper ownership is never adopted by a new start; explicitly stop that
VM first. See [developer lifecycle rules](https://github.com/storytellerF/me/blob/main/DEVELOPMENT.md#vm-lifecycle-and-state-controllers)
for phase transitions and recovery evidence.

## Profile configuration isolation

Profile settings come only from the selected literal `KEY=value` file. Missing
required settings fail validation; missing optional settings use built-in defaults.
Each load replaces the previous file configuration. Profile settings are not
exported to child processes; Testcontainers settings are passed explicitly to
the test command where required. Unknown profile keys are rejected, so profiles
cannot change PATH, HOME or controller/tool selection.

Set VM resources, ports, acceleration, Alpine image/mirror settings, image
preloading, lifecycle timeouts, `FORCE` and `VERIFY_EXISTING` in the profile.
Host controls such as `QEMU_ALPINE_BASE_DIR`, `QEMU_STATUS_PROFILE`,
`QEMU_STATE_PYTHON`, `QEMU_BASH_BINARY`, `GVPROXY_BINARY` and proxy helper paths
remain environment settings. They are not profile keys.


Normal startup creates QEMU directly from Python and records its native process
identity before readiness. A completed start transfers ownership to the persisted
VM state so the VM continues running. Interrupted or unverified publication keeps
the reservation and networking for inspection; older shell-launched records remain
recoverable. Do not remove retained state merely because a PID file is absent.

## Guest provisioning dependencies

The Alpine guest installs `docker`, `docker-cli-compose`, and `openssh` for the
Docker API/CLI, Compose commands, SSH/SFTP, and proxy compilation transport.
OpenRC supplies the `cgroups` service; provisioning enables it with
`rc-update add cgroups default`. Do not add the non-Alpine `cgroupfs-mount`
package. Go is installed only when building the Docker CLI proxy. The outer
Linux runtime reads process identity from `/proc` and does not require `procps`.
The guest installer explicitly includes the supervised Docker wrapper in Alpine's
`lbu` archive so its executable and OpenRC configuration survive system installation.

For a real acceptance check, provision a fresh isolated VM with its own
`QEMU_ALPINE_BASE_DIR`, profile ports, disk, key, and proxy output directory.
After starting it and building its proxy, run from this plugin root:

```bash
bash scripts/run-testcontainers.sh --profile /path/to/isolated.profile -- \
  uv run --script tests/validate-guest-testcontainers.py --pool-start 28000 --pool-end 28015
```

Use the publish-pool bounds from that isolated profile. This opt-in check pulls
BusyBox, Alpine and Ryuk images, exercises HTTP forwarding and CPU/memory cgroup limits,
forces an OOM inside the constrained container, and checks workload removal.
Keep Ryuk enabled. Stop only the isolated VM after verification.
