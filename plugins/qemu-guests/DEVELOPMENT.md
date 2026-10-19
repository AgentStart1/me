# QEMU status panel development

## Windows fallback tool paths

Run `bash ./tests/test-msys2-path.sh` from Git Bash with a separate MSYS2
installation to check fallback path ordering, repeated initialization, existing
command selection, and proxy variable delivery to a child Bash. The test also
starts available QEMU and xorriso binaries for version checks; it does not use a VM.

## gvproxy port allocation audit

The default pool is now 20000–20127 on Windows and Linux. The former 16/256-port
defaults and 512-port ceiling came from the previous networking policy, not a
gvproxy protocol limit. [Upstream v0.9.0's forwarder](https://github.com/containers/gvisor-tap-vsock/blob/v0.9.0/pkg/services/forwarder/ports.go)
keeps a map of listeners and reports actual bind failures. It supports TCP and UDP;
this plugin's profile format and registration remain TCP-only. SCTP is not a
supported forwarder transport. No old QEMU user-networking backend, DNS proxy,
migration workaround, or QEMU listener-count check remains in the runtime.

The review covered shared configuration, guest templates/OpenRC allocator seeding,
host lifecycle and operation leases, test/CLI wrappers, container provisioning,
read-only status/UI, package registration/generation and CI. Changes remove the
port-count policy, batch registrations, handle full outbound-range overlap, reject
guest Docker API collisions even with a remapped host API, require wrapper readiness,
and validate the running rules/pool before host test commands. Acceleration/platform
PID handling, the one-accept QEMU transport, process identity checks, singleton/operation
locks, Ryuk, preserved disks/images and read-only status budgets remain necessary.
Status resource sampling (32 running containers/eight workers) and compact per-container
port lists are presentation/IO budgets, not publish-pool limits. No UI resource
limit was removed to imply greater network capacity.

Local Windows verification with the pinned helper registered and checked 10,000
rules in an isolated process in 3.25 seconds. This proves registration, not 10,000
simultaneous application responses. A separate range hit an occupied host port and
aborted with all partial listeners cleaned. The real helper suite covers 640 rules,
600-rule batch startup, late collision cleanup, invalid input, PID reuse refusal
and restart. Real bare-QEMU lifecycle fixtures cover contention, timeout/TERM,
healthy repeated starts, test leases, exit status and an unchanged sentinel disk.
Configuration/daemon mocks cover the 128-port default, counts beyond 512,
protocol boundaries, outbound fallback, missing wrappers and daemon cleanup.
Controller unit tests cover connection reuse, redirect refusal, batch deadline and
Unix soft/hard descriptor behavior. Status backend, portable/client package and
generation/CLI/workflow checks complete the local regression surface.

The shared persistent guest was leased by an active test operation during this
review, so no real guest restart, allocator migration, fresh ISO install or new
application-load result is claimed. Linux runtime/descriptor tests are part of CI;
local Windows runs cannot establish actual KVM or Linux arm64 behavior. Earlier
migration load results below remain evidence for that earlier version and scope.

## Verification and architecture

Port configuration tests run without QEMU or guest access:

```bash
bash ./tests/test-port-ranges.sh
python3 ./tests/test-gvproxy-control.py
./tests/test-vm-utils.sh
./tests/test-linux-testcontainers.sh
```

The port suite covers the shared 128-port default, explicit pools beyond 512 ports,
gvproxy mappings including controls/custom forwards, duplicate
and reserved ports, outbound range separation, Docker cache initialization and
daemon exit status. Its daemon lifecycle uses mocks; it does not prove a particular
QEMU binary's socket capacity or replace fresh Alpine/OpenRC provisioning validation.

The fixed pool is retained deliberately: all forwarding listeners are ready before
Docker can hand a random port to Testcontainers. An asynchronous Docker event watcher
would introduce a gap between allocation and host connectivity. The default ends
below Alpine's ordinary outbound range and the same policy applies on both platforms.
It is configurable, with no synthetic count ceiling. Guest kernel ephemeral range
validation and a nonempty disjoint outbound range remain necessary; see
[Linux's range checks](https://github.com/torvalds/linux/blob/v6.12/net/ipv4/sysctl_net_ipv4.c).
Moby reads only the range at allocator initialization, not `ip_local_reserved_ports`.
The wrapper must seed a mapping before restoring outbound sysctl; Docker API readiness
alone is insufficient. Old guests lacking that wrapper now fail explicitly.

`gvproxy-control.py start --configure` accepts stdin mappings and keeps registration
inside the process ownership guard and launch cleanup. HTTP requests reuse one
loopback connection, bypass environment proxies, reject non-200 responses including
redirects and do not retry. Each request has a five-second timeout; the batch budget
is 30 seconds plus 20 ms per mapping. Linux startup raises its inherited soft
`RLIMIT_NOFILE` to the listener count plus 256 within the hard limit. It never changes
the hard limit. Connections can require more resources under load. Failed registration
kills the owned helper and removes partial rules through process termination.
The startup wrapper remains under Alpine's stock OpenRC supervisor through
`DOCKERD_BINARY`, so restarts/respawns seed the pool before every daemon execution.
Its readiness check uses the guest Unix socket, independent of host forwarding.
The cache behavior follows [Moby's allocator initialization](https://github.com/moby/moby/blob/v28.5.1/libnetwork/portallocator/portallocator.go);
the binary override follows [Alpine's OpenRC service](https://gitlab.alpinelinux.org/alpine/aports/-/blob/master/community/docker/docker.initd).
API readiness alone does not force lazy allocator initialization. A fresh guest
imports BusyBox plus its musl loader from local files, briefly publishes a container,
checks the automatic port, then removes its own container/image. Restored mappings
already initialize the allocator; no extra pool port is required in that case.
The guest readiness marker is written after outbound restoration and cleared on
wrapper exit; host startup/provisioning and test commands require it. The test
wrapper checks the running helper rules and persisted guest pool before launching
the command, so a new default cannot silently use an old guest's allocation pool.

gvproxy v0.9.0 is pinned with upstream SHA-256 hashes. Source verification uses [the release](https://github.com/containers/gvisor-tap-vsock/releases/tag/v0.9.0), `cmd/gvproxy/config.go`, `cmd/gvproxy/main.go`, and `pkg/virtualnetwork/services.go`. The QEMU socket uses guest `192.168.127.2`, gateway/DNS `.1`, host alias `.254`, and fixed guest MAC `5a:94:ef:e4:0c:ee`. The services endpoint is `/services/forwarder/{expose,unexpose,all}`. Startup validates control/forward collisions and verifies native PID executable plus creation time before cleanup. No QEMU `hostfwd` remains. Launch includes `-ssh-port -1` to disable upstream's implicit 2222 rule; SSH is registered through the API with the profile's other forwards.

Upstream's QEMU accept runs once. Test recovery by stopping both processes, starting both, confirming registered rules and first/middle/last application responses. This also avoids silently reconnecting a VM owned by another user. Readiness polling is limited to startup; protocol probes do not retry failed connections. Windows TCP transport must be validated on actual QEMU; upstream README examples are labelled Linux/macOS.

The operation lease spans lifecycle and client commands, preventing stop/reconfiguration while tests, SSH/SFTP, sync or proxy compilation use the guest. Client children cannot reuse the lease for shutdown. Provisioning retains the singleton reservation between install and verification. INT/TERM exit through one EXIT cleanup, and shutdown retains ownership state on incomplete cleanup. QEMU ownership includes native executable, start time and VM name; Windows holds a native process handle and Linux uses pidfds while signalling. Helper records use exclusive reservation, atomic replacement, generation tokens and a controller guard; readiness verifies listener ownership. Interrupted guards require inspection rather than automatic takeover. Setup participates in serialization and derives a missing public key from its existing private key instead of replacing credentials.

Readiness budgets count actual elapsed time, including probe execution. Loopback HTTP calls bypass proxies explicitly and have per-request deadlines; shared SSH calls enable server-alive checks so a lost guest connection cannot keep an operation lease indefinitely.

The resource collector is separate from test-run metrics. `scripts/status_resources.py`
samples the local system and verified QEMU process through psutil, reads guest counters
using `templates/guest-resource-sample.sh` and the existing SSH key, and derives container
usage from Docker's non-streaming stats endpoint. Every sample has an explicit state;
missing CPU deltas remain null. Container memory subtracts cgroup v1 `total_inactive_file`
or cgroup v2 `inactive_file`, matching Docker's Linux CLI convention. Probe failures
remain scoped to the resource sample and never replace a valid inventory.

`ui/host.mjs` owns immutable snapshots, filtering, refresh coordination and lifecycle
cancellation independently of the DOM. The application injects serial coordination,
tool IO, timer and clock dependencies. Blocking resource IO and CPU sampling run in
the Python MCP server, not the browser event loop. `ui/panel.mjs` adapts Host state to
the view; `ui/view.mjs` formats values. Rebuild `templates/status-panel.html` after UI edits.

From the plugin root:

```bash
npm run build --prefix ui
npm test --prefix ui
uv run --script tests/test-status.py
uv run --script tests/test-status-panel.py
```

The browser suite uses a simulated MCP Apps host and covers resource rendering,
unavailable values, stale snapshots, responsive layout and refresh. Set
`PLAYWRIGHT_CHROMIUM_EXECUTABLE` to an installed Chromium executable if Playwright's
own Chromium is unavailable. It does not establish hardware acceleration or real
guest/cgroup availability; validate those with an already-running VM separately.

Real helper lifecycle/API verification (no guest):

```bash
GVPROXY_BINARY=/path/to/verified/gvproxy python tests/test-gvproxy-lifecycle.py
GVPROXY_BINARY=/path/to/verified/gvproxy python tests/test-vm-lifecycle.py
```

The second fixture runs real bare QEMU and gvproxy without guest disks, with mocked guest IO. It tests competing start/stop/create, coordinated restart, healthy idempotency, TERM/timeout cleanup, client-child shutdown refusal, command exit preservation and an unchanged sentinel disk. Set `QEMU_TEST_BINARY` and `BASH_TEST_BINARY` for non-default installations. CI installs QEMU and runs both fixtures on Linux.

For application verification on an idle, already-running Windows VM with Go and cached `postgres:11-alpine`:

```bash
uv run --script tests/validate-gvproxy-network.py
```

This opt-in probe requires the default loopback SSH/API/control ports. It registers 70 same-port HTTP forwards (21000–21069), checks all responses three times, and performs 320/640 PostgreSQL connections at concurrency 8/16 without connection retries. It accepts matching pre-registered profile rules for restart verification. It cleans only its own fixtures and extra rules. Run ordinary/custom-network container DNS probes separately. The Linux runtime image contains the verified helper so its unprivileged, network-disabled smoke test needs no download. CI exercises the real helper lifecycle and port-range suites.

Validated migration evidence (Windows x86-64, upstream gvproxy v0.9.0 and installed QEMU 11.0.1): the existing disk boots with WHPX, DHCP selects `.2`/gateway `.1`, guest DNS and both ordinary/custom Docker-network DNS succeed, and the unauthenticated Docker API responds through loopback. With 91 simultaneous rules, all 70 HTTP ports respond in three rounds (210/210), including first/middle/last ports. PostgreSQL reconnect probes pass 320/320 at concurrency 8 and 640/640 at concurrency 16. The same results pass after coordinated QEMU/gvproxy restart with rules restored from the profile. No connection failure retries are added.

The Windows Docker CLI proxy passes its guest Go tests and native build, and builds the Linux runtime image. Its non-root, capability-free, network-disabled TCG smoke test passes with verified gvproxy preinstalled. The real helper and QEMU lifecycle fixtures pass on both Windows and Linux; Linux restart checks cover TIME_WAIT reuse without weakening Windows bind exclusivity. Shutdown refuses a live lifecycle/client lease. Existing shell utilities (131 assertions), status (16 cases), panel and UI Host (5 cases) suites pass, along with portable/client package validation and package-generation/CLI/workflow tests. PostgreSQL readiness waits for the final container-local TCP server, excluding the image's temporary Unix-only init server. Fresh ISO provisioning, actual KVM availability and Linux arm64 execution were not exercised in this migration; keep those distinct from validated existing-disk and x86-64 runtime behavior.

Downstream server verification completes after plugin/runtime checks: three focused cases pass, then the full suite passes 175 tests (174 passed, zero failures/errors, one existing skip), with JDK 21 and unchanged assertions/timeouts. The full command takes 1247 seconds including image tasks.

## Concurrent work-guest controller

`guest_config.py` validates JSON profiles independently of Alpine shell profiles. `guest_seed.py` renders private unattended media from `templates/guests/` using pycdlib. `guest-vm.py` supervises a foreground native QEMU process with a per-state-directory lease. Signal deferral covers process creation and record publication. Stop requests carry a session token; failed cleanup retains ownership evidence. Work guests do not acquire the Alpine backend reservation.

Install `scripts/requirements-guests.txt`, then run `python tests/test-work-guests.py`. The suite checks Ubuntu/Windows media generation, checksum rejection, forwarding, incomplete-disk preservation and duplicate-session exclusion. With native QEMU installed it runs two paused QEMU instances concurrently and verifies independent stop/cleanup. Controlled acceptance in that process smoke test does not establish successful OS installation. Actual OS and Docker/Testcontainers acceptance require corresponding images, backend, target proxies and adapter configuration.

Default acceptance checks guest SSH and Docker server access; Ubuntu also checks cloud-init completion. Custom adapters own installation and acceptance. The status MCP App also reads the work-guest registry and exposes a separate app-only PNG capture tool. All generated guest files belong in private state directories, never in this repository. Backend storage retains the legacy path after renaming. Explicit proxy targets write to OS/architecture subdirectories and retain the user-wide build lease.

## Graphical guests and macOS installation

`guest_registry.py` stores one atomic public descriptor per normalized state directory. Status verifies both QEMU and supervisor native identities and matching tokens. `guest_screen.py` resolves only registered IDs and checks QMP listener ownership before bounded PNG capture; it deletes private temporary files on success/failure. `ScreenHost` owns selection, polling, visibility and late-result rejection independently of rendering. No remote HTTP/VNC server or input tool is exposed by the panel.

Run `python tests/test-guest-panel.py`, `npm test --prefix ui`, `npm run build --prefix ui`, and the existing status protocol/browser suites. Native tests exercise actual paused QEMU screen capture and cleanup. Browser tests check guest rows, headless suppression and frame polling. `tests/validate-work-guests.py --profile /path/ubuntu.json --profile /path/windows.json --report /private/report.json` is opt-in real acceptance: it requires already-ready independent guests, runs guest-local Docker context builds concurrently, verifies loopback API and published HTTP, captures graphical screens and removes only its own labeled containers/images. Use distinct publish ports because all guests share the same daemon.

macOS preparation uses Apple tools on a preparation Mac. The runtime controller in `macos_install.py` only opens the Recovery terminal after bounded OCR and sends the fixed seed script path. A durable handoff marker prevents destructive retry. Seed scripts refuse partitioned target disks. Product package payload runs account/SSH/Docker setup as a first-boot LaunchDaemon. Tests validate generated scripts/control events; actual installer compatibility must be checked with matching firmware and media. Preparation scripts and installed package have not been exercised on macOS when no preparation Mac is available; do not report them as installed or validated merely from rendering tests.

## Work-guest integration evidence

Windows 11 build 26200 with QEMU 11.0.1/WHPX ran three independent work guests concurrently: Ubuntu 24.04 with XFCE/LightDM, headless Ubuntu 24.04 and Windows Server 2025 Desktop Experience. Each guest built a private Docker context, reached the shared Linux daemon API and fetched its own published HTTP response. Both graphical guests returned real PNG frames; the headless guest had no screen endpoint. Stopping one work VM preserved the other VMs and backend. A fresh Windows installation completed unattended through two supervised cold boots after correcting the stock SSH firewall rule's Private-only profile.

Historical Windows WHPX comparison: four vCPUs stalled under QEMU 11.0.1, whose CPU-model argument is ignored. One vCPU booted successfully. QEMU 11.1 with `Westmere,-vmx,-svm` cold-booted the retained Windows disk with four guest-visible processors; default and host models failed. Guest warm reset still produced VP exit code 4 during BIOS startup. Disabling the interrupt controller did not provide a working alternative. The new Windows default instead uses four vCPUs with the managed partition-reset build described below. Explicit legacy system-runtime profiles can retain a clean-exit cold-boot budget. Unexpected exits are not retried, and no accelerator fallback occurs. Graphical supervisors observe QMP paused state so a surviving paused native process cannot remain labelled ready; paused screens remain inspectable.

### WHPX four-vCPU Windows reboots

`scripts/whpx_runtime.py` owns the integrated build/cache/bundle. Source SHA-256 and the patch are pinned; patch plus shell-template content select a separate cache directory. The build takes an exclusive directory reservation and retains it on console cancellation for process inspection. Source checksum or compiler failures never launch a guest. Fresh extraction uses Python's data filter and excludes symlinks and unused firmware source/CI trees. Build orchestration lives in `templates/build-whpx-qemu.sh`, not generated shell strings. The builder packages the PE dependency closure from UCRT64 plus source firmware, writes file hashes and atomically publishes the runtime only after verification. It preserves failed workspaces and never mutates system QEMU.

Every managed launch verifies the complete file manifest and checks `-accel help` reports WHPX only. `guest_config.py` selects the managed runtime by default for Windows guests on Windows when no custom executable is specified. `guest-vm.py` prepares it before acquiring a VM lease; read-only plan resolves the future executable/firmware paths without building. Status and stop use only persisted guest ownership and remain usable without compilers or a runtime cache. Managed profiles reject executable overrides, untested CPU/accelerator arguments and cold installer budgets. On Linux explicitly use the system runtime/KVM. Python 3.12+ is needed for safe extraction; MSYS2 UCRT64 supplies native build dependencies. `qemu-img` remains a normal host prerequisite.

Run `python tests/test-whpx-runtime.py` for cache corruption, forbidden TCG binaries, cache reuse, failure propagation, read-only planning and four-vCPU default contracts. `python scripts/whpx_runtime.py --archive C:/private/qemu-11.1.2.tar.xz --msys2-root C:/msys64 --jobs 8` exercises the same build path using an already-downloaded archive; it still verifies the pinned hash. A successful repeated invocation verifies and returns the cache without compiling again.

Stock QEMU 11.1.2 reproduced the four-vCPU reset failure on Windows 11 build 26200 with a Windows Server 2025 BIOS/MBR guest. Q35/SeaBIOS, a smaller BIOS and masking x2APIC still failed. A GPT-converted disposable overlay booted under Q35/EDK2 but hung on reset; its base disk was not converted. Disabling the WHPX interrupt controller did not complete Windows startup. These results do not establish a generic Windows guest configuration problem.

`patches/qemu-11.1.2-whpx-partition-reset.patch` adapts [Mohamed Mediouni's proposed reset hook](https://patchew.org/QEMU/20260421205749.55060-1-mohamed@unpredictable.fr/) to release 11.1.2, checking/logging the reset HRESULT. All vCPUs are stopped, then the accelerator resets its partition before QEMU restores CPU registers. [Microsoft's API contract](https://learn.microsoft.com/en-us/virtualization/api/hypervisor-platform/funcs/whvresetpartition) explains that this clears per-VP pending state while preserving GPA mappings and backing memory. On x64 it requires Windows 11. The callback warns if the API is unavailable; that case is not a successful fix. An unsuccessful HRESULT must be investigated rather than treated as a passed reset.

Use the integrated CLI above rather than maintaining separate manual build flags. The pinned hash records the official source archive used in verification, not an independent publisher signature. Firmware comes from the release's prebuilt `pc-bios` files; dependent non-system DLLs are packaged beside the executable, so managed launches do not need MSYS2 directories on PATH. The tested build used GCC 16.2, Meson 1.12 and Ninja 1.13.

On an idle, already-ready four-vCPU Windows guest, this opt-in command requests real guest restarts; it never starts QEMU or changes acceleration:

```powershell
python tests/validate-whpx-reboots.py --profile C:/private/windows.json --report C:/private/reboots.json
```

It checks the supervised native identity and QMP listener, compares Windows boot times across three `shutdown /r` requests, rejects paused/replaced QEMU processes, confirms four logical processors after every reboot, and finally runs guest Docker CLI/API acceptance. Polling only waits for post-reboot SSH readiness; an unsuccessful cycle is not restarted. Reports belong outside the repository. Separately run `validate-work-guests.py` for concurrent builds and published-port acceptance.

For real status-panel verification, keep at least two graphical guests and one headless guest ready and run:

```powershell
uv run --script tests/validate-live-panel.py --profile C:/private/windows.json --profile C:/private/ubuntu-desktop.json --profile C:/private/ubuntu-headless.json --output-dir C:/private/panel --chromium "C:/Program Files/Google/Chrome/Application/chrome.exe"
```

This serves the actual generated panel through a temporary loopback MCP Apps host bridge backed by the source status/screen functions, not simulated snapshots. It verifies ready cards/resources, absence of a headless screen button, and repeated graphical selection with PNG data matching each requested guest. Reports and panel screenshots stay in the private output directory. This checks source UI integration; the installed Codex panel receives the new code after distribution publication and a new chat loads the updated plugin.

The initial patched-runtime probe passed three consecutive warm reboots in the same native QEMU process (18.50, 18.55 and 18.52 seconds to the first successful SSH boot-time probe), followed by guest Docker CLI/API acceptance. The reusable probe then passed another three restarts, four-processor checks and Docker CLI/API acceptance in that same process. No TCG code was built. This establishes the reset fix for the tested BIOS/MBR, CPU model and host/guest combination; the stock binary, Windows 10 and patched UEFI remain separate cases.

The integrated builder was then exercised from a fresh source workspace and packaged a standalone runtime whose accelerator list contains only WHPX. A new four-vCPU Windows Server 2025 graphical installation completed unattended with zero supervisor cold relaunches and the same native QEMU identity from initial setup through final Docker acceptance. Two fresh Ubuntu 24.04 work VMs (XFCE and headless) also provisioned unattended under explicit WHPX. All three simultaneously built guest-local Docker contexts, accessed the shared API and fetched their own published HTTP responses. Stopping/restarting the headless guest preserved both graphical processes. The new Windows installation passed three more warm reboots (43.05, 27.59 and 20.64 seconds including processor checks), then the three-guest Docker acceptance passed again. The real source status panel passed Windows-to-Ubuntu-to-Windows switching with matching QMP PNG frames, correct ready/resource cards and no headless screen button. These are source-panel/browser bridge checks; installed-client loading follows distribution publication.

Windows system OpenSSH subprocesses stalled on stdin/output when the Docker proxy was invoked through a guest SSH login. Windows proxy command IO now uses `golang.org/x/crypto/ssh` directly, retaining the existing private-backend host-key policy and remote exit codes. Linux/macOS keep the system client. The transport test covers binary data, EOF, multiple sessions, remote failure status and commands completing with unused open stdin; it passes on native Windows and under Alpine's race detector. Go 1.26 is required for the pinned dependency. Real cross-OS acceptance passed after this change. Keys, media, generated credentials, detailed reports and screenshots stay outside the repository.

### Experimental macOS Recovery on WHPX

Reference [OSX-KVM](https://github.com/kholia/OSX-KVM/tree/4c378a4b5e0b219783683012bec680325eb40719) for OpenCore, firmware and SATA layout, rather than copying its Linux KVM accelerator/CPU flags. The tested source was that commit. Its manual Disk Utility installation is not unattended provisioning.

On the tested Intel Windows 11 host, QEMU 11.1.2 plus the reset patch reached XNU but Sonoma Recovery (Darwin 23.6.0) panicked at `cpu_threads.c:198`: `Zero divisor: topoParms.nCoresSharingLLC`. Enable OpenCore boot arguments `-v keepsyms=1 debug=0x108 serial=3` and capture QEMU's serial output to distinguish this panic from a firmware hang. The separate [cache-topology patch](patches/qemu-11.1.2-whpx-cache-topology.patch) adds CPUID leaf 4 to WHPX's exit list, letting the existing QEMU CPUID handler supply the selected CPU model's deterministic cache topology. Applying it to the same reset-patched source and rebuilding passed this panic and reached the English Sonoma Recovery screen with four vCPUs. The unchanged managed Windows binary was kept separate; this experimental patch is not applied by the integrated builder yet.

The successful probe used explicit `whpx,hyperv=off,kernel-irqchip=off`, `Skylake-Client,-hle,-rtm,vendor=GenuineIntel,-vmx,-svm,-hypervisor,+invtsc,vmware-cpuid-freq=on`, Q35, 4 GiB RAM, four cores in one socket, qemu-xhci USB keyboard/tablet, Apple SMC, upstream OVMF with a private writable variables copy, snapshot OpenCore and Recovery disks on AHCI SATA ports 2/3, a separate empty target on port 4, vmxnet3 without an option ROM, and vmware-svga. These parameters describe one probe, not a general compatibility promise or a minimal required set. No TCG was compiled or used. Repeat without disabling the Hyper-V features before deciding whether those debug options are necessary.

Shift-Command-T opened Recovery Terminal. Batched key presses/releases produced lost releases and repeated characters; separated down/up events with 150 ms polling intervals executed commands correctly. The controller uses this spacing, releases modifiers on interruption, and requires a shell prompt before handoff.

A subsequent installation-only probe downloaded the official Sonoma 14.8.9 (23J631) InstallAssistant package on Windows, unpacked its installer app, transferred the shared-support package to Recovery, and invoked `startosinstall --volume --installpackage --agreetolicense --nointeraction` on a dedicated empty 64 GiB work disk. It completed installation with four guest-visible logical processors, 4 GiB memory, graphical login and Finder/Dock, public-key SSH, first-boot markers and registered read-only QMP capture. The same native QEMU identity survived installer reboots. A later QMP hardware reset and a Recovery repair were needed to finish the initial bootstrap; these are not evidence of an entirely unattended source-adapter run or a clean guest-requested restart test. Other Windows/Ubuntu work guests remained ready. macOS Docker proxy validation was explicitly omitted.

The catalog package `Digest` matched SHA-1 of the compressed XAR table of contents, not the whole package. All 1,303 SHA-256 blocks matched the integrity data fetched from Apple's HTTPS endpoint. Its signature method 2 supplies a self-hash, not a digital signature; do not describe it as a signed chunklist. Recovery's `hdiutil verify` passed and `pkgutil --check-signature` reported signed Apple Software. This is separate from the previously signature-verified Recovery chunklist. Keep media hashes and native reports outside the repository.

The probe exposed two bootstrap boundaries. Boot-time package installation wrote a LaunchDaemon after launchd's startup directory scan; writing a plist alone did not start it. The product package now includes a postinstall hook that bootstraps the service only when the target is `/`, preserving preparation/Recovery hosts. Native `pkgbuild`/`productbuild` and package expansion were exercised on the installed Mac with an inert fixture; recorded launchctl doubles verified alternate-target isolation and bootstrap/kickstart handling without loading a real service. The updated complete Docker payload was not installed in that check.

Native SSH accepted the key, then closed with `Access denied ... by PAM account configuration`. Adding the work user to the existing `com.apple.access_ssh` group resolved it. First boot now does that without creating a new restriction when the group is absent. Per-user Setup Assistant preferences also avoid showing the accessibility/cloud screens after account creation. A QEMU keyboard identification prompt was dismissed after confirming keyboard input worked; accelerated graphics and arbitrary releases remain outside this validation. The bundled adapter still needs prepared full installer media and a bootstrap package, and the cache-topology patch remains experimental rather than part of the default managed Windows build. Keep images, firmware variables, account credentials and detailed logs private.
