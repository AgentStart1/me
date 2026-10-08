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
- `scripts/build-docker-proxy.sh`: cross-compile and download the native Docker CLI proxy using Go inside Alpine
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
tests, cross-compiles Windows amd64 with CGO disabled, and downloads the executable over SSH.
The host needs no Go installation. Go and its caches remain on the persistent guest disk;
temporary source and binaries are cleaned up after success or failure. `run-testcontainers.sh` places the resulting
native proxy on PATH and supplies SSH settings. Set `QEMU_DOCKER_PROXY_DIR` consistently in both
scripts to override the helper directory. Restart existing Gradle daemons if their executable
lookup does not reflect the updated PATH.

The proxy filters local `docker build` contexts with Docker's upstream `moby/patternmatcher`,
including ordered exceptions and Dockerfile-specific ignore files. It streams the resulting tar
over SSH to guest `docker buildx build --load`. Non-build commands execute through SSH without
context copying; host-path bind mounts and `docker cp` are not translated. Build secrets, SSH
mounts and named host contexts require explicit transport support and are rejected. Keep secrets
excluded by Docker ignore rules. The skill never selects project service names or Docker targets.

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

Keep the environment launcher from the Bash installation that started the wrapper.
Do not replace it with another MSYS2 installation's `env.exe` after changing `PATH`:
native Windows SSH can exit 255 before initialization when runtimes are mixed.

## Configuration and recovery

Read [`references/configuration-and-recovery.md`](references/configuration-and-recovery.md)
when changing profile values, port forwarding, acceleration, mirrors, image preloading,
resource metrics, bind-mount behavior, or incomplete provisioning recovery.

## Validation

```bash
./tests/test-apk-mirror-selection.sh
./tests/test-vm-utils.sh
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
