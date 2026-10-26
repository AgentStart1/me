---
name: qemu-guests
description: Use when provisioning or managing concurrent QEMU work guests as Appium test environments alongside an independent Alpine Docker backend. Includes unattended Ubuntu cloud images, Windows answer files, Intel macOS Recovery automation, custom installation adapters, graphical guest screens, host Appium connections, backend status and Testcontainers on Windows or Linux. Do not trigger for ordinary Docker workflows.
---

# QEMU Guests

## Project independence

Keep this AI plugin's launcher paths, VM/backend profiles, credentials and lifecycle procedures outside consuming projects. Projects declare portable artifact/service roles and standard Docker/Appium requirements; do not add QEMU/AI-plugin-specific runtime branches or documented helper invocations merely to run tests. Return native diagnostics through the application-side service instead of making clients detect the VM provider. Required Appium drivers/extensions, Gradle plugins and other real project dependencies must still be declared and documented. Explicitly requested provider integration is limited to that requested scope.

## Work guests and shared Docker backend

Read the concurrent work VM and custom adapter sections of the plugin README before provisioning work guests. Use `scripts/guest-vm.py install|run|stop|status|plan <guest.json>`. Guest JSON profiles are distinct from Alpine `.profile` files. Multiple work VMs may run simultaneously, each with an independent state directory, disk, lease and host SSH port. Work guests do not require the Alpine backend. Do not install Docker proxies or backend credentials in work guests; host Docker/Testcontainers remains independent.

Work VMs are runtime/test environments. Unless the user explicitly requests guest compilation, compile applications, test code, native dependencies and installation hooks on the host or an existing designated build environment, then transfer built artifacts and prebuilt dependencies. Requests to install a guest, configure Appium or run tests do not authorize compiling in the work VM. Never silently fall back to guest compilation or increase its CPU/RAM to accommodate a build; resolve host-side build prerequisites or report the limitation.

Ubuntu uses verified cloud-init images. Windows uses BIOS/MBR amd64 unattended answer files for compatible media. Intel macOS uses prepared Apple installer media and a bootstrap product package: bounded OCR waits for Recovery, keyboard automation opens Terminal, and the attached script invokes `startosinstall` on the explicitly configured empty guest disk (matched by serial when selected). The package postinstall hook explicitly loads first boot on the running target only. First boot configures the user, existing SSH access-group membership, per-user setup preferences and Appium per-user LaunchAgent, preconfigures the standard emulated USB keyboard as ANSI, clears the installer’s one-time auto-login flag before enabling persistent automatic login, then reboots. Build the private product package and ISO with the macOS preparation scripts. Do not claim Apple Silicon IPSW or arbitrary release compatibility. Custom systems still need explicit automation/acceptance. Do not substitute installer clicking for unattended installation; report missing prerequisites precisely.

Apple Recovery images can be downloaded on Windows with OpenCore's macrecovery tool and verified against Apple's signed chunklist; an existing Mac is not required for downloading Recovery. Distinguish this from the full installer app/ISO and private product package required by the current adapter. The macOS example now explicitly selects WHPX, but its CPU arguments and private OpenCore/firmware remain release-specific. A separate experimental CPUID-cache runtime completed a four-vCPU Sonoma 14.8.9 installation and SSH/desktop checks under WHPX with a private installation-only adapter and bootstrap repairs; A later explicitly authorized Xcode 16.2 / Mac2 4.5.0 check built WebDriverAgentMac and passed a host-connected Finder session, native source, screenshot and menu-click smoke test; consuming-project end-to-end acceptance and an entirely unattended source-adapter run remain separate. See DEVELOPMENT.md before reproducing it; do not substitute the experimental binary for the managed Windows runtime. Never silently fall back to TCG or report Recovery download as successful macOS installation.

Prepare Appium with `scripts/build-appium-runtime.py` on the same guest OS/CPU platform. Pin project-required drivers explicitly (Windows desktop example: `--driver appium-desktop-driver@2.8.0`). Supply the archive, checksum and unique host port in the profile's `appium` object. Connect using `scripts/connect-appium.py`; verify the first SSH host-key fingerprint. Windows uses a persistent auto-login test account and an interactive logon task so applications open only on the guest desktop. Stage application artifacts and arrange backend reachability through the consuming project's own test tooling. Never bake project paths, app packages, test commands, credentials or a particular project's SDKs into this plugin. Mac2 UI sessions require compatible full Xcode, a prepared WebDriverAgentMac build and Accessibility permission for the built runner and Xcode Helper. Command Line Tools alone is insufficient. Obtain explicit guest-build authorization before allowing Mac2 to invoke xcodebuild; otherwise use a designated build environment and prebuilt WDA endpoint. Validate a real native session/source/screenshot/click separately from server readiness. On macOS without a selected developer toolchain, preserve the launcher’s missing-tool handling so the optional Git revision probe cannot open a developer-tools installer. Never install build tools just to satisfy that probe. A ready Appium server alone does not prove that a project's end-to-end test passed. Manual guest testing needs a separate interactive console; the panel stays read-only.

Set the JSON `graphical` boolean to select desktop components (Ubuntu XFCE/LightDM or Windows Server Desktop Experience versus Core). Give graphical guests distinct `qmp_port` values bound only to loopback. The status panel lists registered work VMs and shows selectable live read-only screens; it never sends keyboard/mouse input. `qemu_guest_screen` is app-only and accepts a registered guest ID, verifying native identity and QMP listener ownership. Ordinary snapshots contain no image data; temporary capture files are removed. Headless macOS still needs private QMP for Recovery automation.

Ensure the guest desktop fits the suite's largest window at its configured DPI. Basic macOS framebuffers may expose only the boot-selected mode; set the private OpenCore UEFI Output Resolution when necessary, retain its original configuration, restart and verify the actual mode. Do not change display geometry during a test run. macOS can disconnect SSH before kernel shutdown completes; do not treat that disconnect alone as proof of completed shutdown; wait for the guest to finish before forcing the owned QEMU process to exit.

Windows defaults to four vCPUs and `qemu_runtime: "whpx-reset"` on Windows 11 x64. `install`/`run` build or verify the managed QEMU 11.1.2 runtime, including private DLLs and firmware; only WHPX is compiled. Use Python 3.12+ and MSYS2 UCRT64 (`QEMU_MSYS2_ROOT` for nonstandard host locations). `scripts/whpx_runtime.py` can prepare it ahead of time. Build/checksum/accelerator failures are terminal; never fall back to TCG. `plan`/`status`/`stop` never build. Keep the tested `Westmere,-vmx,-svm` CPU arguments, no explicit `qemu` override and no `install_reboots` cold-boot budget for the managed runtime. On Linux hosts, profiles must select the system runtime and KVM explicitly. The independent host Docker proxy uses Go SSH transport to avoid nested system-SSH stdin/output stalls.

Read DEVELOPMENT.md for managed-runtime provenance, build recovery and verification. The bundled local partition-reset patch adapts an upstream proposal; stock 11.1.2 still failed on the tested host. The CET/XSAVE patch also bounds WHPX CET bits by the selected model and guest XSAVE/XSAVES support; never re-enable host CET on Westmere. Validate actual guest flags as well as boot readiness, and preserve crash disks/RAM privately when investigating init panic. Never replace system QEMU implicitly. Cached runtime files are hashed before execution, and recipe changes create a separate cache. Keep each build bound to its single immutable BuildSnapshot through cache selection, compilation, packaged inputs, manifest and verification. Changes to source templates/patches belong to later invocations; never re-fingerprint or relabel an in-flight build. Inspect remaining build processes before clearing an interrupted build lock. Validate guest boot-time changes, four guest-visible processors and unchanged QEMU native identity with `tests/validate-whpx-reboots.py`, then authenticated Appium readiness and concurrent work-guest acceptance. Each reboot must also recover the interactive Appium service within the same cycle deadline; SSH returning first is not acceptance. Cold supervisor relaunches do not count as warm reboot success. Legacy explicit system-runtime profiles may retain a bounded `install_reboots` budget; never mistake those for the default managed path. Do not generalize the result to Windows 10, other CPU models or UEFI installations without testing them.

Use `guest-vm.py status` for individual work guests. Never provision a VM merely to populate status. Stop only the requested guest, preserving other guests and the backend. Keep the foreground supervisor alive; use another terminal for stop/status. Preserve incomplete disks, seed media and uncertain process ownership. Never automatically retry a recorded macOS destructive handoff. Work-guest seeds contain guest account credentials and SSH authorization; keep them private and out of repositories and logs.

On ordinary Linux hosts, use Docker directly for Docker-only workflows. Work-guest supervision also runs on Linux with QEMU. Backend scripts retain their existing Windows/Linux-container behavior and legacy storage paths.

## macOS first-boot and media checks

Use a GPT installer disk (GPTSPUD in the preparation helper), attached read-only through USB; do not treat a partitioned Apple image as an ISO9660 CD. Configure OpenCore to boot the installer/target automatically and hide its own EFI self-entry. Resolve the actual Recovery mount path for startosinstall and the explicitly empty target disk; prefer a configured QEMU disk serial because BSD disk numbers can change between boots. Host-side OCR uses the pinned Pillow dependency to enlarge frames before strict prompt matching. Generated shell seeds must retain LF on Windows.

First boot requires FileVault off, publishes dedicated-account loginwindow credentials with root-only permissions, installs the Appium LaunchAgent and reboots. Never disable encryption to satisfy setup. Acceptance must confirm authenticated SSH, the expected console user, its loaded Appium service and ready loopback endpoint. A handoff marker is not installation success; retain it and inspect failures rather than repeating a destructive command. No compiler or native install hook may run in the work guest without explicit user authorization.

On Sequoia, a retained `/var/db/.AppleSetupTermsOfService` cookie can force the
Terms pane even when `.AppleSetupDone` and persistent automatic login exist.
The first-boot template clears this separate cookie for the installation already
invoked with `--agreetolicense`. Do not substitute clicking the Terms pane for
validating the corrected bootstrap on an independent empty disk.

## Project runtime requirements and setup hooks

Keep portable dependency requirements in the consuming project: Java/Appium versions, normal driver/plugin dependencies, system runtime libraries, prebuilt native classpath coordinates and desktop dimensions. Keep VM hardware, media, SSH, accelerator settings, prebuilt bundle locations and operator launcher commands outside that project. Use `prepare-appium-runtime.py` to package prepared local extensions, prebuilt assets and the Windows host-compiled display helper. `--requirements` with `--platform` also executes project-declared host preparation hooks. Use `guest-vm.py install <private-profile> --requirements <project-requirements>` for automated desktop setup. Fresh initialized Linux guests supply their prepared JDK/native metadata without a private Linux transport override. Use new isolated state directories/disks/ports for acceptance; never reset an existing VM to validate an install.

Project `hooks.host_prepare` may build/download/stage on the host. Project `hooks.guest_setup` may run self-contained initialization scripts after offline runtime extraction, with explicit arguments and bounded timeouts. Review scripts before running them. Guest hooks configure runtime state and install prebuilt dependencies; they do not grant permission to compile in the work guest. Never encode consuming-project scripts or commands in this plugin. Fail and preserve private logs when hooks fail or time out; do not skip failed initialization. Prepare all shared host artifacts before running E2E and keep them immutable during active UI tests.

Keep large archives out of cloud-init YAML: extract the seed payload from read-only media instead. Poll cloud-init status without creating long-lived waiters. Verify SSH host-key pins using the supervised QEMU-owned listener and preserve the per-VM pin for later connections. The isolated Linux test display is distinct from the console framebuffer shown in the panel.

## Unified host test environments

Use `bash scripts/run-test-env.sh --config <project-environment.json> -- <host test command>` to combine the existing Docker/Testcontainers environment and transparent guest Appium proxy. Keep project-specific property roles, cleanup roots and environment selections in project configuration; the plugin must not contain application names or paths. Use shell-free SSH forwarding channels and confirm every forward acknowledgement; never keep remote shells waiting on stdin. Roll back a newly created Appium session if output handoff fails, retaining ownership when deletion is uncertain. Keep Windows SSH scripts on the bounded stdin transport; do not inline growing suite artifact lists into encoded command-line arguments. The proxy adapter supports quoted JVM argument files for Windows host/guest and Windows/Linux host to Linux guest. Previously prepared/custom Linux environments can use an operator-owned TEST_ENV_LINUX_RUNTIME override containing a dedicated POSIX mirror root, an existing guest Java executable and prebuilt host native classpath additions (plus an optional Appium port). Prepare an isolated graphical Appium session, D-Bus/AT-SPI and an unlocked test keyring outside the project. Map declared file/directory roles and classpaths, send launch capabilities to the guest Java runtime, and collect outputs back to their original host paths. Never ship the host Windows JDK into Linux or build missing native libraries in the guest. It stages classpath/JDK/agent artifacts after host compilation, mirrors private input/output files, forwards declared loopback service ports, preserves guest state across application restarts, and cleans owned state at command completion. Never compile in the work VM without an explicit user request. Fail unsupported adapters instead of guessing. Run native diagnostics through Appium on the application machine and return results directly; never make clients attach to guest PIDs locally. Keep provider paths and private VM/backend profiles out of consuming projects. Supply connections through operator-owned `TEST_ENV_DOCKER_PROFILE` / `TEST_ENV_GUEST_PROFILE`; project JSON declares workspace and launch roles, including optional prebuilt `artifacts`. The old `run-testcontainers.sh` forwards to the new entry point for compatibility; do not introduce another separate test launcher.

## Design invariants

- Use the bundled persistent Alpine VM with unprivileged gvproxy networking inside Linux Docker containers and on Windows.
- Run at most one Alpine backend at a time; multiple work VMs are allowed. Backend scripts serialize lock-state updates with an atomic guard and enforce a backend VM lock.
- Whole-operation leases also protect setup and VM clients from concurrent lifecycle changes. Do not bypass a busy lease. After forced termination, confirm all plugin lifecycle/client processes have exited before removing interrupted `run/vm-operation.lock`, `vm-state.guard` or a helper `.control.lock`; preserve process records until both owned processes are confirmed stopped.
- Cleanup verifies QEMU/gvproxy native executable and creation time before signalling. Healthy repeated starts check forwarding rules, SSH, Docker and the publish pool. For Windows provisioning and legacy shell records, use the launching Bash runtime for path/PID conversion; normal native starts keep their original PIDs; bypass HTTP proxies explicitly for `127.0.0.1` instead of passing a wildcard to curl.
- Missing PID pointers do not prove QEMU exit. Recover partial publication through the pending launch PID and native identity; retain networking and reservations when publication or inspection remains unknown. See the configuration and recovery reference for profile lifecycle options.
- Follow the lifecycle snapshot's phase and reservation generation. Before creation, clean only this launch's resources; after creation, verify QEMU exit before stopping its helper. Never adopt existing helper ownership or bypass a recovery-required reservation. A completed ready VM survives cancellation of the already-completed start; a cancelled stop can be resumed with another owned stop.
- Resource creation and cleanup share one cancellation handoff rule: defer handled signals through handle assignment or definitive failure rollback. Failed initial metadata publication removes only the guard created by that call. Helper cancellation joins the owned process before removing pending state; failed kill/join retains evidence. Never apply this rollback to a pre-existing guard or helper reservation.
- For CLI-to-Shell claims, generate the token and install matching cleanup before acquisition. Join the native creator before cancellation rollback, retain custom cleanup traps, and release only the same owner/token. Use the shared shell facade; the internal begin/guard-acquire CLI requires a caller-known token. Failed delivery does not authorize removal of an existing unknown lease or guard.
- In auto mode, probe KVM with `-cpu host` on Linux or WHPX with `-cpu host` on Windows. Fall back to multi-threaded TCG with `-cpu max` if hardware acceleration is unavailable. Explicit `kvm`/`whpx` must fail clearly instead of silently falling back.
- Use gvproxy v0.9.0 over a loopback TCP QEMU socket with either accelerator; preserve MAC `5a:94:ef:e4:0c:ee`.
- Bind every host forward to `127.0.0.1`.
- Reuse the persistent qcow2 disk so Docker images survive between test runs.
- Resolve Alpine and Docker upstream DNS through gvproxy at `192.168.127.1`.
- Keep Testcontainers Ryuk enabled.
- Pass the profile's extended Testcontainers pull pause and total timeouts to host test processes because large image extraction can be quiet under TCG fallback.
- Use platform-aware `auto` resource metrics: collect Windows/guest metrics through PowerShell on Windows; run Linux commands without that collector. Preserve test exit codes. Explicit `true` requires the Windows collector.
- Keep Docker's automatic published-port range equal to the gvproxy same-port forwarding range.
- `auto` selects 128 ports from the configured start on both platforms (20000-20127 by default). Do not impose a port-count ceiling. Validate the guest kernel range (1024–65535), outbound space and host/guest service collisions. gvproxy registers all TCP mappings before QEMU starts, using one controller and persistent HTTP connection; failed registration cleans the owned launch. Linux hard `nofile` limits and actual host binds remain resource constraints. UDP/SCTP publishing is not forwarded by these scripts.
- Docker caches its publish pool on daemon initialization. New guests seed it through the supervised startup wrapper, then restore a disjoint broad outbound kernel range. Do not apply new defaults by changing only QEMU forwards or restarting another session's persistent guest; review publish-pool compatibility in the README.
- Never silently delete an incomplete disk or use `docker image prune -a`.
- Treat TCP port 2375 as a root-equivalent, unauthenticated API; do not expose it beyond loopback.
- Render provisioning configuration from `templates/*.tpl` with the shared `render_template` helper; keep scripts limited to runtime values and orchestration.

## Paths

- `scripts/setup.sh`: prerequisites and verified Alpine ISO download
- `scripts/create-vm.sh`: unattended install and post-boot verification
- `scripts/select-apk-mirror.sh`: first-provisioning mirror detection, HTTPS validation, and official-CDN fallback
- `scripts/start-vm.sh`: background start with automatic or explicitly selected acceleration
- `scripts/stop-vm.sh`: graceful or forced shutdown
- `scripts/run-test-env.sh`: unified configured host tests with Docker and transparent guest Appium transport
- `scripts/build-docker-proxy.sh`: cross-compile and download the native Docker CLI proxy using Go inside Alpine
- `scripts/collect-resource-metrics.ps1`: Windows host and Alpine guest resource sampler used by the Testcontainers wrapper
- `scripts/run-docker.sh`: guest Docker CLI over SSH
- `scripts/sync-workspace.sh`: copy a host workspace into the guest over SSH without running project commands
- `scripts/connect-vm.sh`: connect to the guest through an interactive SSH or SFTP session
- `scripts/vm-utils.sh`: stable shared-utility facade and common path initialization
- `scripts/lib/`: focused runtime, configuration, template, QEMU, guest, Alpine-image, and VM-state modules loaded by the facade

- `templates/`: Alpine answers, guest setup, sysctl, and Docker daemon configuration templates
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

Ensure ISO downloads, disk provisioning and VM startup are covered by the user's
request or prior authorization. Ask only when that scope is missing; do not repeat
approval for an already authorized operation. Ownership and operation leases still apply.

Initial setup:

```bash
./scripts/setup.sh
./scripts/create-vm.sh ./profiles/dev.profile
```

Daily testing:

```bash
./scripts/start-vm.sh ./profiles/dev.profile
./scripts/build-docker-proxy.sh # once, and after proxy source updates
./scripts/run-test-env.sh -- <test command>
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

On Windows, append fallback MSYS2 tool directories to `PATH` so existing Bash and tool choices
retain priority; do not prepend another installation's runtime.

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

## Upstream improvement feedback

- When using this plugin reveals an actionable bug, missing guidance, or reusable improvement, report it to [storytellerF/me](https://github.com/storytellerF/me/issues). Identify the owning plugin and skill; do not report project-specific problems without evidence that the plugin needs a change. Finish the user's primary task before non-blocking feedback work.
- Before any search or submission, reduce the finding to a privacy-safe summary. Never send raw conversations, private source code, logs, screenshots, credentials, personal identifiers, account data, or private paths/URLs. Use synthetic examples and the minimum non-sensitive environment details needed to explain the problem. If safe disclosure is impossible, keep the finding local.
- Search both open and closed upstream issues using the plugin name and sanitized symptom keywords. Read likely matches and their resolution; do not rely only on title matches. Reuse a matching issue link instead of opening a duplicate. Add a comment only when it supplies materially new, safe evidence and posting is authorized. A closed issue warrants a new report only for a distinct regression or uncovered case, with a link explaining the difference.
- Submit a new issue when no duplicate exists and the user has authorized upstream reporting in the current session or standing instructions. This rule alone does not authorize external posting. Honor existing authorization without asking again; otherwise prepare a sanitized draft for approval.
- Include the plugin/skill and version, observed and expected behavior, a minimal synthetic reproduction or concrete improvement proposal, and relevant duplicate-search results. Use a concise title prefixed with the plugin name.
- If search, authentication, or submission fails, retain the sanitized draft and explain the blocker; do not post without completing duplicate checks. After an uncertain submission result, check for the created issue before retrying. Return the existing or created issue URL, or clearly mark the report as an unsubmitted draft.

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

Provisioning remains shell orchestration in `create-vm.sh`, using the same Python
state controller for operation leases, global reservations, process registration
and state cleanup. Guest templates and simple command forwarding remain shell.
Unknown process probes, interrupted guards and failed cleanup retain ownership
for inspection. On Windows use Ctrl+C or native Ctrl+Break for graceful
cancellation; Git Bash `kill -TERM` forcibly terminates native Python and cannot
run cleanup. Inspect any remaining operation lease before manual recovery.

## File-only profile settings

Read VM settings directly from the selected profile. Do not set VM configuration,
lifecycle timeouts, `FORCE`, `VERIFY_EXISTING`, ports or provisioning options through
environment variables; inherited values are ignored. Missing required file values
fail, while optional values use built-in defaults. Profile values are non-exported
shell configuration; only explicit tool/test contracts receive derived settings.
Unknown keys are rejected. Keep host/tool controls such as `QEMU_ALPINE_BASE_DIR`,
profile/interpreter selection, `GVPROXY_BINARY` and proxy helper paths in the host
environment. See the plugin README for the configuration boundary.


Normal startup creates QEMU directly from Python and records its native process
identity before readiness. A completed start transfers ownership to the persisted
VM state so the VM continues running. Interrupted or unverified publication keeps
the reservation and networking for inspection; older shell-launched records remain
recoverable. Do not remove retained state merely because a PID file is absent.

## Guest dependency and acceptance checks

For the qualified Windows 11 x64 / Intel macOS 15.8.1 GPU path, use the bundled
`qemu_runtime: "reims-whpx"` profile and `scripts/reims_runtime.py`, not cached
private experimental binaries or sibling source checkouts. This runtime is
separate from Windows guests' `whpx-reset`. Its dependency pins and patches live
in `patches/reims-windows`; first use builds public sources with GNU Rust and
MSYS2 UCRT64 and verifies the complete runtime. Use
`uv run scripts/prepare-macos-gpu-boot.py` to create a new operator-owned EFI
copy with the bundled, guarded timing fix and pinned Lilu; require build 24H32.
Do not modify a running boot image, overwrite firmware, bypass a failed driver
hash/build guard, or claim support for a new macOS release. Keep all caches,
Apple media, private firmware, profiles and credentials outside consuming
projects. Read README.md for prerequisites and DEVELOPMENT.md for rebuilding
the supplied driver on a designated preparation machine. This does not grant
guest-build authorization. Require actual clock/framebuffer and unchanged
business acceptance; native SDL presentation and video decode are unqualified.
Use one normal in-guest shutdown request for cold-boot qualification and confirm
native exit before relaunching; do not race ACPI and SSH shutdown requests.
The transparent `java-argfile` relay supports Windows/Ubuntu only. macOS business
acceptance requires a prepared operator-owned Appium launch adapter; do not
claim the GPU runtime adds that transport or place provider details in the project.

For Intel macOS desktop recovery after fresh installation or explicit upgrade,
read README.md's prepared-desktop section and use `scripts/macos-desktop.py
prepare|reconcile|verify <guest.json> --plan <private-desktop.json>`. Use prepare
before a planned cold boot; it does not publish desktop readiness. Require a reviewed
exact OS build, bundle identifiers/CDHashes, pinned artifacts and an independent
prebuilt WDA LaunchAgent. Use `webDriverAgentMacUrl`, never an Appium-managed WDA
process or a build-for-testing fallback. Scripts, credential ZIPs and specific
GPU/business checks stay outside consuming projects. The source WDA template
only executes test-without-building. Probe actual access with a fresh reviewed
runner before repairing permissions; preserve working grants. Regrant missing
Accessibility through native System Settings controls and narrowly recognized authentication; do not edit TCC or
disable system security. Require actual input readback, native window geometry,
screenshot and confirmed cleanup before desktop readiness. Cold-boot verification
and the unchanged business suite remain separate from SSH/Appium readiness.
Prepare the dedicated account before cold boot to prevent idle screen locking.
Require a verified unlocked matching console before native input; do not bypass
an existing lock or treat a ready SSH/Appium service as proof of an unlocked UI.
Reconciliation may perform one normal account login only after checking the
matching locked console, system loginwindow secure-input process and visible
password field. Never delete lock cookies or weaken authentication policy;
verification must not authenticate and must require actual unlocked state.
For permission authorization, require one recognized password field and the
reviewed System Settings/SecurityAgent process in the test account to own secure input; recheck the prompt and process
identity before typing once. Never replace these checks with OCR text alone or
blind input into the current focus. Publish terminal desktop receipts after
resource/worker cleanup while still holding the guest lease; a retained lease
always requires inspection regardless of a prior receipt's phase.
Retain uncertain session leases; inspect named resources before operator recovery,
without bulk-deleting sessions or stealing reservations.

Require a complete CPU-matched Mac2 runtime as well as WDA; a server-only Appium
archive can report ready without any drivers. The desktop controller imports the
prepared Mac2 entry before session creation. Preserve diagnostic failures and
retained ownership records when moving validation to a new independent guest.

Use Alpine's OpenRC `cgroups` service, not a `cgroupfs-mount` package. Retain
Docker, Compose and SSH/SFTP dependencies; Go is needed only for proxy compilation.
For real provisioning validation, use a new isolated base directory, disk, key,
ports and proxy directory. Run `tests/validate-guest-testcontainers.py` through
`run-testcontainers.sh` after provisioning/startup and proxy compilation; supply
that profile's publish-pool bounds and keep Ryuk enabled. See the README for the
exact command. The check verifies forwarding, cgroup limits, OOM enforcement and
container removal; it does not authorize changes to another session's VM.

Validate runtime platform and x64 architecture before new installation; do not infer them from the host OS or accept missing metadata. Preserve existing VM records: guest-hook fingerprint v2 requires a new isolated initialization for older hook-based environments, while no-guest-hook fingerprints stay compatible. Lost, malformed or interrupted Appium creation responses require retaining the cleanup-uncertain lease and private inputs until the operator confirms remote cleanup; never clear that lease or bulk-delete sessions automatically.

Use TestEnvironmentOwner for the lease and all guest-test resources. Persist retention at the resource failure boundary before other cleanup runs; later exceptions must never unlock an uncertain environment. Use the immutable initialization snapshot for requirements, script bytes, fingerprint, preflight and seed generation. Never re-read hook paths during seed assembly, mutate detached views to change a captured install, or serialize script bytes into the VM metadata record. Verify these contracts with the isolated owner/snapshot suites; leave native QEMU smoke disabled unless explicitly authorized.

GuestTransport owns its SSH children: attempt every child stop before reporting aggregate cleanup failures. Preserve cancellation after draining cleanup and retain the environment lease on failure. Verify with tests/test-transport-cleanup.py using mocks; never start existing VMs for this regression.

Configured test execution must share one CancellationRequest between CLI, TestEnvironmentOwner and transports. Follow the three invariants in DEVELOPMENT.md: only the main thread commits cancellation/phase/lease state; workers publish reliable events and sticky cleanup failures; release and terminal publication require closed admission, confirmed resource-worker completion and final event collection. Signals only enqueue requests. Workers read committed snapshots at checkpoints and never construct or replace shared cancellation. Keep main-thread cleanup shields context-local. Report stop failures before HTTP conversion and worker completion, retaining them even if a later retry succeeds. Reject worker attempts to mutate owner/CLI state. Preserve existing assertions and the documented cancellation priority, including the identity of an accepted interruption. Never reintroduce frame inspection, asynchronous signal exceptions, handoff retries or nested handler replacement. Keep the shared process runtime and existing VM-management commands unchanged.

Publish one immutable CliResult/CleanupReport after worker reports and all cleanup have been accounted for. Emit fixed failure categories/counts and the accurate acquired-lease recovery hint, never raw cleanup exceptions, commands, paths or credentials. Unconfirmed workers or failed retention publication must preserve ownership evidence. Verify tests/test-worker-protocol.py plus the existing cancellation, CLI, owner, transport and relay suites with QEMU_TEST_ACCEL unset. Use mocks/local fixtures; do not start, stop or repair existing VMs for these regressions.
