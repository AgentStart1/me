---
name: qemu-alpine-docker
description: Use when creating, starting, stopping, troubleshooting, or viewing status for a persistent QEMU Alpine Docker VM inside Linux Docker containers or on Windows. Includes KVM, WHPX, and TCG workflows for Docker and Testcontainers; On Linux hosts outside containers, use Docker directly without this plugin; do not trigger for ordinary Docker workflows.
---

# QEMU Alpine Docker

## Current scope

For now, use this plugin for Linux Docker container environments and Windows environments. On Linux hosts running outside containers, use Docker directly without provisioning a QEMU VM through this plugin.

## Design invariants

- Use the bundled persistent Alpine VM with unprivileged gvproxy networking inside Linux Docker containers and on Windows.
- Run at most one plugin VM at a time. The scripts serialize lock-state updates with an atomic guard and enforce a global VM lock.
- Whole-operation leases also protect setup and VM clients from concurrent lifecycle changes. Only migration explicitly shares its lease with nested stop/start. Do not bypass a busy lease. After forced termination, confirm all plugin lifecycle/client processes have exited before removing interrupted `run/vm-operation.lock`, `vm-state.guard` or a helper `.control.lock`; preserve process records until both owned processes are confirmed stopped.
- Cleanup verifies QEMU/gvproxy native executable and creation time before signalling. Healthy repeated starts check forwarding rules, SSH, Docker and the publish pool. On Windows use the launching Bash runtime for path and PID conversion; bypass HTTP proxies explicitly for `127.0.0.1` instead of passing a wildcard to curl.
- In auto mode, probe KVM with `-cpu host` on Linux or WHPX with `-cpu qemu64` on Windows. Fall back to multi-threaded TCG with `-cpu max` if hardware acceleration is unavailable. Explicit `kvm`/`whpx` must fail clearly instead of silently falling back.
- Use gvproxy v0.9.0 over a loopback TCP QEMU socket with either accelerator; preserve MAC `5a:94:ef:e4:0c:ee`.
- Bind every host forward to `127.0.0.1`.
- Reuse the persistent qcow2 disk so Docker images survive between test runs.
- Resolve Alpine and Docker upstream DNS through gvproxy at `192.168.127.1`; remove Unbound and DHCP DNS overrides during explicit existing-disk migration.
- Keep Testcontainers Ryuk enabled.
- Pass the profile's extended Testcontainers pull pause and total timeouts to host test processes because large image extraction can be quiet under TCG fallback.
- Use platform-aware `auto` resource metrics: collect Windows/guest metrics through PowerShell on Windows; run Linux commands without that collector. Preserve test exit codes. Explicit `true` requires the Windows collector.
- Keep Docker's automatic published-port range equal to the gvproxy same-port forwarding range.
- Keep the existing automatic publish range: `auto` resolves to 20015 on Windows or 20255 on Linux. Preserve explicit ranges up to 512 ports; gvproxy registers every mapping explicitly.
- Docker caches its publish pool on daemon initialization. New guests seed it through the supervised startup wrapper, then restore a disjoint broad outbound kernel range. Do not apply new defaults by changing only QEMU forwards or restarting another session's persistent guest; plan migration using the README.
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
- `scripts/build-docker-proxy.sh`: cross-compile and download the native Docker CLI proxy using Go inside Alpine
- `scripts/collect-resource-metrics.ps1`: Windows host and Alpine guest resource sampler used by the Testcontainers wrapper
- `scripts/run-docker.sh`: guest Docker CLI over SSH
- `scripts/sync-workspace.sh`: copy a host workspace into the guest over SSH without running project commands
- `scripts/connect-vm.sh`: connect to the guest through an interactive SSH or SFTP session
- `scripts/vm-utils.sh`: stable shared-utility facade and common path initialization
- `scripts/lib/`: focused runtime, configuration, template, QEMU, guest, Alpine-image, and VM-state modules loaded by the facade

- `templates/`: Alpine answers, guest setup, sysctl, and Docker daemon configuration templates
- `scripts/migrate-vm-network.sh`: explicit migration preserving existing disk and images
- `scripts/lib/gvproxy.sh` and `scripts/gvproxy-control.py`: verified helper lifecycle, readiness, forwarding registration and cleanup
- `profiles/dev.profile`
- `tests/test-vm-utils.sh`
- `tests/test-apk-mirror-selection.sh`

## Linux containers

Read `container/README.md` at the plugin root for the ordinary, non-root container workflow. KVM can be enabled with `/dev/kvm` device access and the matching supplementary group; do not require `--privileged`. Use TCG if KVM is unavailable. Keep the test process, QEMU, and MCP status server in the same outer container's process/network namespace. Preserve loopback-only Docker and Testcontainers forwards. The guest is x86-64; KVM requires a compatible Linux host CPU.

## Read-only status panel

For requests to view VM state, service health, or containers, call `qemu_docker_status` to open **VM & Containers** in hosts supporting MCP Apps. It has an `openai/ui` global sidebar and thread entrypoints and takes no arguments. The global entrypoint adds a left-sidebar launch item; the thread entrypoint opens it beside a conversation. Refresh remains within the panel. Never start a VM or provision resources merely to populate this view.

Without MCP Apps support, run `scripts/status.py` with Python 3 and summarize its JSON snapshot. Read `QEMU_STATUS_PROFILE` for a custom profile and `QEMU_ALPINE_BASE_DIR` for existing state overrides; do not invent a running state from the ready marker. Unknown probes, unavailable lists, and stale PID files must be reported as such. SSH health means a banner was received, not successful authentication. Resource counts and accelerator policy are profile configuration, not measured utilization. The separate accelerator field is read from the running process when available.

The separate `resources` snapshot reports live host-system, QEMU-process, and Alpine-guest CPU/memory; each container's `resources` reports CPU/memory when running. These are refresh samples, not the test wrapper's metrics report. Host/QEMU CPU is normalized over host logical CPUs; guest CPU is normalized over guest CPUs; container CPU uses 100% per core. Linux host-system values reflect the kernel system view, not an outer container's cgroup allocation. Preserve unavailable and not-running states and null CPU baselines. Guest sampling uses only the existing key and fixed read-only `/proc` commands over loopback SSH. Never create keys or install guest tools to populate the panel. The MCP runtime includes psutil; plain Python needs it for host/process samples. Container probes are bounded to 32 running containers with eight workers.

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
./scripts/build-docker-proxy.sh # once, and after proxy source updates
./scripts/run-testcontainers.sh -- <test command>
./scripts/stop-vm.sh ./profiles/dev.profile
```

After starting the VM, run `scripts/build-docker-proxy.sh` (optionally with `--profile <path>`).
It uses existing SSH to transfer source, installs Go in Alpine if missing, runs native guest
tests, builds for Windows amd64 or Linux amd64/arm64 according to the environment running
the script with CGO disabled, and downloads the executable over SSH. Run both compilation
and tests on Windows or inside the same outer Linux container as QEMU; no Go installation
is needed in that environment. Go and its caches remain on the persistent guest disk;
temporary source and binaries are cleaned up after success or failure. `run-testcontainers.sh` places the resulting
native proxy on PATH and supplies SSH settings. Set `QEMU_DOCKER_PROXY_DIR` consistently in both
scripts to override the helper directory. Restart existing Gradle daemons if their executable
lookup does not reflect the updated PATH.

The proxy filters local `docker build` contexts with Docker's upstream `moby/patternmatcher`,
including ordered exceptions and Dockerfile-specific ignore files. It streams the resulting tar
over SSH to guest `docker buildx build --load`. Non-build commands execute through SSH without
context copying; host-path bind mounts and `docker cp` are not translated. Build secrets, SSH
mounts and named host contexts require explicit transport support and are rejected. Keep secrets
excluded by Docker ignore rules. On Windows, archive permissions add execute bits and remove
group/world write bits; in Linux containers, source permission bits are preserved, so ensure
scripts already have their required execute bits. The skill never selects project service names or Docker targets.

When project files must exist inside the guest, sync them separately and then run the project's own build or test command:

```bash
./scripts/sync-workspace.sh --remote-dir /root/my-project /path/to/project
```

The sync command excludes common generated and private paths by default, accepts repeated `--exclude` options, and never runs a project-specific build.

The start script returns after SSH and the Docker API are ready. The test wrapper sets:

- `DOCKER_HOST=tcp://127.0.0.1:<DOCKER_DAEMON_PORT>`
- `TESTCONTAINERS_HOST_OVERRIDE=127.0.0.1`
- `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock`

It unsets TLS variables and `TESTCONTAINERS_RYUK_DISABLED` and preserves the test command's exit code. With `auto` metrics, Windows collects and reports resource averages and peaks; Linux runs without the PowerShell collector and does not update the metrics report.

On Windows, keep the environment launcher from the Bash installation that started the wrapper.
Do not replace it with another MSYS2 installation's `env.exe` after changing `PATH`:
native Windows SSH can exit 255 before initialization when runtimes are mixed.

## Configuration and recovery

Read [`references/configuration-and-recovery.md`](references/configuration-and-recovery.md)
when changing profile values, port forwarding, acceleration, mirrors, image preloading,
resource metrics, bind-mount behavior, or incomplete provisioning recovery.

## Validation

On Windows, the status collector translates Git Bash/MSYS PIDs before verifying the native QEMU process and accelerator. A missing process is stopped; failed inspection remains unknown. Rebuild the panel with Node on Windows or Linux after UI changes.

```bash
./tests/test-apk-mirror-selection.sh
./tests/test-vm-utils.sh
bash ./tests/test-port-ranges.sh
./tests/test-sync-workspace.sh
./tests/test-build-docker-proxy.sh
./scripts/build-docker-proxy.sh
```

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

The default proxy directory is user-wide: `~/.local/share/me/docker-proxy`.
Windows uses `docker.exe`; Linux containers use `docker`. Every project under the same
user in that environment uses the same executable; the wrapper supplies that run's VM SSH settings.
In Linux containers, the directory belongs to the container user. Persist it or rebuild
the helper after replacing the outer container; the persistent VM disk alone does not retain it.

For network recovery, coordinate `stop-vm.sh` then `start-vm.sh` after confirming no other user owns the VM. Upstream accepts one QEMU connection; restarting both restores rules and establishes a fresh transport. Never hide application failures with connection retries or SSH networking bridges.
