# Independent Alpine Docker backend

Use this route only when the tests need this backend. Reuse a suitable existing Docker endpoint; on ordinary Linux hosts use Docker directly. Work guests do not require Alpine, and Docker-only tests do not require a work guest. Read the plugin [prerequisites](../../../README.md#prerequisites) before setup.

## Provision and run

Run the following only for a new backend covered by the request:

```bash
scripts/setup.sh
scripts/create-vm.sh /absolute/path/to/backend.profile
```

For an existing backend, reuse it or start it with `scripts/start-vm.sh /absolute/path/to/backend.profile`. Prepare the native Docker CLI proxy when missing or after proxy source updates with `scripts/build-docker-proxy.sh --profile /absolute/path/to/backend.profile`, then run host tests with `scripts/run-test-env.sh --profile /absolute/path/to/backend.profile -- <test command>`. Use the configured workflow in [test execution](test-execution.md) when coordinating guest Appium as well. Stop the backend only when requested and ownership permits; do not stop a reused service merely because a test finished.

The proxy builder is a live operation, not an offline check: it connects to the existing Alpine backend, transfers source, installs Go there if needed, runs Go tests there, cross-compiles a native proxy for the selected host target, and downloads it over SSH. Invoke the builder and host test command on Windows or in the same outer Linux container as QEMU. Go and its caches remain on the persistent Alpine disk; temporary source and binaries are cleaned after success or failure. This backend tooling build is separate from compilation in a Windows/Ubuntu/macOS work guest.

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

Set `QEMU_DOCKER_PROXY_DIR` consistently for builder and test wrapper overrides. The wrapper places the proxy on PATH and supplies SSH settings; restart an existing Gradle daemon only when it retained obsolete executable lookup. The proxy uses Go SSH transport to avoid nested system-SSH stdin/output stalls.

## Backend configuration

Read [configuration and recovery](configuration-and-recovery.md) before changing profiles, acceleration, port ranges, metrics, mirrors, preloaded images or recovery settings. Backend `.profile` files are distinct from work-guest JSON profiles. At most one Alpine backend may run at once; multiple work guests remain independent.

The rules below apply to Alpine. In particular, its `auto` accelerator fallback does not apply to explicitly selected or managed work-guest runtimes.

- Use gvproxy v0.9.0 over a loopback TCP QEMU socket with either accelerator; preserve MAC `5a:94:ef:e4:0c:ee`.
- Reuse the persistent qcow2 disk so Docker images survive between test runs.
- Resolve Alpine and Docker upstream DNS through gvproxy at `192.168.127.1`.
- Keep Testcontainers Ryuk enabled.
- Pass the profile's extended Testcontainers pull pause and total timeouts to host test processes because large image extraction can be quiet under TCG fallback.
- Keep Docker's automatic published-port range equal to the gvproxy same-port forwarding range.
- Docker caches its publish pool on daemon initialization. New guests seed it through the supervised startup wrapper, then restore a disjoint broad outbound kernel range. Do not apply new defaults by changing only QEMU forwards or restarting another session's persistent guest; review publish-pool compatibility in the README.
- Never silently delete an incomplete disk or use `docker image prune -a`.
- Treat TCP port 2375 as a root-equivalent, unauthenticated API; do not expose it beyond loopback.

## Docker files and build contexts

The proxy filters local `docker build` contexts with Docker's upstream `moby/patternmatcher`,
including ordered exceptions and Dockerfile-specific ignore files. It streams the resulting tar
over SSH to guest `docker buildx build --load`. Non-build commands execute through SSH without
context copying; host-path bind mounts and `docker cp` are not translated. Build secrets, SSH
mounts and named host contexts require explicit transport support and are rejected. Keep secrets
excluded by Docker ignore rules. On Windows, archive permissions add execute bits and remove
group/world write bits; in Linux containers, source permission bits are preserved, so ensure
scripts already have their required execute bits. The skill never selects project service names or Docker targets.

Docker build options may precede or follow the context directory. Explicit `-f`/`--file`
paths resolve from the host working directory and must stay inside the context.
`--iidfile` writes the image ID back to the requested host path after a successful build.
Relative output paths resolve from the host working directory; their parent directory must exist.
The guest uses a private temporary file and cleans it after transfer or build failure.
`--metadata-file` and `--output`/`-o` remain unsupported and are rejected.

When project files must exist in Alpine, `scripts/sync-workspace.sh --remote-dir <guest-directory> <host-workspace>` copies them with default generated/private-file exclusions and optional repeated `--exclude` flags. It never runs a project command. Copying a workspace is not permission to compile application code in a work guest; keep the requested build/test placement explicit.

The start script returns after SSH and the Docker API are ready. The test wrapper sets:

- `DOCKER_HOST=tcp://127.0.0.1:<DOCKER_DAEMON_PORT>`
- `TESTCONTAINERS_HOST_OVERRIDE=127.0.0.1`
- `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock`

It unsets TLS variables and `TESTCONTAINERS_RYUK_DISABLED` and preserves the test command's exit code. With `auto` metrics, Windows collects and reports resource averages and peaks; Linux runs without the PowerShell collector and does not update the metrics report.

## Linux-container host

Read `container/README.md` at the plugin root for the ordinary, non-root container workflow. KVM can be enabled with `/dev/kvm` device access and the matching supplementary group; do not require `--privileged`. For this Alpine backend, automatic acceleration may select TCG when KVM is unavailable; an explicit accelerator must fail instead of falling back. Keep the test process, QEMU, and MCP status server in the same outer container's process/network namespace. Preserve loopback-only Docker and Testcontainers forwards. The guest is x86-64; KVM requires a compatible Linux host CPU.

## Lifecycle and recovery

Use Python 3.10+ to run `scripts/start-vm.py` or `scripts/stop-vm.py` with the same
optional profile argument. The `.sh` commands select an interpreter and retain
the launching Bash runtime through `QEMU_BASH_BINARY`; native callers may set
that variable explicitly. Set `QEMU_STATE_PYTHON` for an explicit interpreter.
Start/stop own readiness, cancellation and failure cleanup in Python. Process
signalling still verifies native executable and creation time through the
shared process identity implementation. The platform/guest adapter plans acceleration
and networking and runs SSH commands without owning lifecycle locks. Python owns
native helper controller subprocesses through cancellation and exit.

Provisioning remains shell orchestration in `create-vm.sh`, using the same Python
state controller for operation leases, global reservations, process registration
and state cleanup. Guest templates and simple command forwarding remain shell.
Unknown process probes, interrupted guards and failed cleanup retain ownership
for inspection. Apply the common cancellation rules and inspect any remaining operation lease before manual recovery.

For network recovery, coordinate `stop-vm.sh` then `start-vm.sh` after confirming no other user owns the VM. Upstream accepts one QEMU connection; restarting both restores rules and establishes a fresh transport. Never hide application failures with connection retries or SSH networking bridges.

## Live backend acceptance

Use Alpine's OpenRC `cgroups` service, not a `cgroupfs-mount` package. Retain
Docker, Compose and SSH/SFTP dependencies; Go is needed only for proxy compilation.
For real provisioning validation, use a new isolated base directory, disk, key,
ports and proxy directory. Run `tests/validate-guest-testcontainers.py` through
`run-testcontainers.sh` after provisioning/startup and proxy compilation; supply
that profile's publish-pool bounds and keep Ryuk enabled. See the README for the
exact command. The check verifies forwarding, cgroup limits, OOM enforcement and
container removal; it does not authorize changes to another session's VM.
