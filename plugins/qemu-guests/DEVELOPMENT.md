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

`scripts/whpx_runtime.py` owns the integrated build/cache/bundle. Source SHA-256 and the ordered patches are pinned; patch names/content plus shell-template content select a separate cache directory. The build takes an exclusive directory reservation and retains it on console cancellation for process inspection. Source checksum or compiler failures never launch a guest. Fresh extraction uses Python's data filter and excludes symlinks and unused firmware source/CI trees. Build orchestration lives in `templates/build-whpx-qemu.sh`, not generated shell strings. The builder packages the PE dependency closure from UCRT64 plus source firmware, writes file hashes and atomically publishes the complete tree after file verification. It executes the accelerator probe at the final path before returning the executable; executing the staged PE first can leave Windows image/antivirus handles that prevent directory rename. It preserves failed workspaces and never mutates system QEMU.

`BuildSnapshot` owns one immutable capture of source version/URL/checksum, build-template bytes and ordered patch names/bytes. A build captures once before selecting its cache; location, compiler inputs, packaged template/patches, manifest and both verification boundaries receive that same snapshot explicitly. No later step re-reads operator-controlled template/patch paths. The verified source archive is copied into the unique workspace before checksum verification and extraction, so replacing the external archive cannot change the bytes extracted after verification. Failed workspaces and their private input copies remain inspectable.

Unchanged captured inputs retain the existing recipe algorithm and cache identity, allowing previously verified runtimes to remain usable. A later invocation captures current inputs afresh and selects its own recipe. Do not relabel an older binary with a later snapshot or retry a failed build under a different recipe. The mutation fixtures use only temporary directories and simulated compilation/accelerator probes: edits before compilation, deletion during compilation, external archive replacement, failure after mutation, missing input before cache side effects, one capture per build and frozen fields. No fixture starts QEMU or changes an operator cache/VM.

Every managed launch verifies the complete file manifest and checks `-accel help` reports WHPX only. `guest_config.py` selects the managed runtime by default for Windows guests on Windows when no custom executable is specified. `guest-vm.py` prepares it before acquiring a VM lease; read-only plan resolves the future executable/firmware paths without building. Status and stop use only persisted guest ownership and remain usable without compilers or a runtime cache. Managed profiles reject executable overrides, untested CPU/accelerator arguments and cold installer budgets. On Linux explicitly use the system runtime/KVM. Python 3.12+ is needed for safe extraction; MSYS2 UCRT64 supplies native build dependencies. `qemu-img` remains a normal host prerequisite.

Run `python tests/test-whpx-runtime.py` for cache corruption, forbidden TCG binaries, cache reuse, failure propagation, read-only planning and four-vCPU default contracts. `python scripts/whpx_runtime.py --archive C:/private/qemu-11.1.2.tar.xz --msys2-root C:/msys64 --jobs 8` exercises the same build path using an already-downloaded archive; it still verifies the pinned hash. A successful repeated invocation verifies and returns the cache without compiling again.

Stock QEMU 11.1.2 reproduced the four-vCPU reset failure on Windows 11 build 26200 with a Windows Server 2025 BIOS/MBR guest. Q35/SeaBIOS, a smaller BIOS and masking x2APIC still failed. A GPT-converted disposable overlay booted under Q35/EDK2 but hung on reset; its base disk was not converted. Disabling the WHPX interrupt controller did not complete Windows startup. These results do not establish a generic Windows guest configuration problem.

`patches/qemu-11.1.2-whpx-partition-reset.patch` adapts [Mohamed Mediouni's proposed reset hook](https://patchew.org/QEMU/20260421205749.55060-1-mohamed@unpredictable.fr/) to release 11.1.2, checking/logging the reset HRESULT. All vCPUs are stopped, then the accelerator resets its partition before QEMU restores CPU registers. [Microsoft's API contract](https://learn.microsoft.com/en-us/virtualization/api/hypervisor-platform/funcs/whvresetpartition) explains that this clears per-VP pending state while preserving GPA mappings and backing memory. On x64 it requires Windows 11. The callback warns if the API is unavailable; that case is not a successful fix. An unsuccessful HRESULT must be investigated rather than treated as a passed reset.

`patches/qemu-11.1.2-whpx-cet-xsave.patch` fixes the WHPX leaf-7 handler re-enabling host CET bits after QEMU has filtered the selected CPU model. The result is the intersection of model and WHPX support, and requires the guest XSAVE/XSAVES save/restore path; unrelated bits and dynamic OSPKE handling remain unchanged. Both patches are included in the hashed runtime bundle and cache recipe. Remove this local patch only after the pinned upstream source enforces the same contract and the native/runtime acceptance passes.

A retained Ubuntu 24.04 guest exposed `user_shstk` and `ibt` despite lacking `xsave`/`xsaves`; init later panicked on a user shadow-stack page fault. A separate old-runtime overlay reproduced init panic after 2,394 seconds. Linux prints the page-fault error in hexadecimal: `44`/`46` include the shadow-stack bit, not decimal error 44/46. [Linux's CPUID dependencies](https://github.com/torvalds/linux/blob/v6.8/arch/x86/kernel/cpu/cpuid-deps.c) require XSAVES for SHSTK; see also the [shadow-stack documentation](https://www.kernel.org/doc/html/next/x86/shstk.html). Faulting guest state remains private; do not publish RAM dumps, disks or raw logs. This evidence motivates the patch, while direct SSP context history was not captured.

A fresh independent fixed-runtime Ubuntu completed 7,222.22 seconds of host-timed stress, 1,195,225 runtime cycles and 240 health samples without panic or worker errors. Guest CPUID omitted SHSTK/IBT/XSAVE/XSAVES under Westmere, shadow-stack enable returned EOPNOTSUPP, and systemd, authenticated SSH and Appium stayed healthy with unchanged native QEMU identity. This is a bounded acceptance window, not proof of indefinite stability. The same uninterrupted instance then passed the full consumer desktop suite (15 application and 3 panel cases, no failures/errors/skips) with unchanged assertions/timeouts; host compilation and remote runtime execution remained separate. A separate fresh Windows Server 2025 installation using the same fixed runtime then passed three four-core warm reboots in 50.73, 53.09 and 70.98 seconds, each recovering authenticated Appium within the unchanged 180-second deadline and preserving native QEMU identity. A host-built native CPUID probe in Windows confirmed SHSTK/IBT/XSAVE/XSAVES were all absent.

Run `python tests/test-whpx-runtime.py` with a native C compiler on the host. The matrix compiles the helper extracted from the shipped patch and checks all model/host/XSAVE/XSAVES combinations for both CET masks, including preservation of unrelated bits. Cache and publication tests ensure patch changes select a new recipe and staged file checks execute no PE. Hardware acceptance must use separate profiles/disks/ports, confirm actual guest flags and shadow-stack rejection, complete at least two hours of runtime stress and the consuming suite, then recheck four-core Windows warm reboots. Keep existing VM processes and crash scenes untouched; no guest compilation or TCG fallback is permitted.

Use the integrated CLI above rather than maintaining separate manual build flags. The pinned hash records the official source archive used in verification, not an independent publisher signature. Firmware comes from the release's prebuilt `pc-bios` files; dependent non-system DLLs are packaged beside the executable, so managed launches do not need MSYS2 directories on PATH. The tested build used GCC 16.2, Meson 1.12 and Ninja 1.13.

On an idle, already-ready four-vCPU Windows guest, this opt-in command requests real guest restarts; it never starts QEMU or changes acceleration:

```powershell
python tests/validate-whpx-reboots.py --profile C:/private/windows.json --report C:/private/reboots.json
```

It checks the supervised native identity and QMP listener, compares Windows boot times across three `shutdown /r` requests, rejects paused/replaced QEMU processes, confirms four logical processors after every reboot, and waits for guest Appium acceptance after each reboot within the same cycle deadline. SSH availability alone does not establish that the interactive Appium service has started; an unsuccessful cycle is not restarted. Reports belong outside the repository. Separately run `validate-work-guests.py` for concurrent builds and published-port acceptance.

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

## Independent Appium work guests

Work guest profiles now require `appium` (runtime archive, SHA-256 and distinct host tunnel port) and reject the removed `backend` / `proxy_binary` fields. Seeds contain no Docker proxy or Alpine key. The Alpine host Docker workflow remains independent. Guest acceptance checks authenticated SSH and the loopback Appium readiness response, plus cloud-init on Ubuntu. Windows persists its dedicated test-account login and starts Appium as an interactive scheduled task; SSH Session 0 never launches desktop applications. macOS installs a user LaunchAgent and requires a user login before Appium acceptance. Linux server readiness does not establish X11/AT-SPI driver compatibility; consuming projects own those prerequisites.

The runtime builder pins Appium and accepts explicit npm driver/plugin versions. It creates relocatable private metadata; guest relocation rewrites extension install paths using YAML parsing. The service starts Appium in its own Node process so stopping the scheduled service cannot orphan a wrapper child. Windows stdout/stderr are captured directly to avoid Windows PowerShell interpreting native diagnostic stderr as terminating errors. Project plugins, JDKs, application paths, backend service forwarding and test selection remain outside this plugin.

Validation: the Windows runtime builder and guest upgrade were exercised with Appium 3.2.2 / DesktopDriver 2.8.0. A host-run desktop end-to-end signup case passed against a four-vCPU WHPX guest; guest Docker was not used. Separate guest-side window checks covered foreign-process filtering, DPI-aware 800x600 resizing, an untitled modal dialog through standard remote switching, and return to the main frame. This evidence does not claim fresh unattended Appium provisioning or Linux/macOS Appium UI validation. Earlier Docker guest validation sections describe the superseded work-guest mode.

Work-guest resource policy: compilation defaults to the host or the existing designated build environment, with only prebuilt artifacts/dependencies transferred into work VMs. Guest compilation (including dependency installation hooks that build native code) requires an explicit user request. Installing a VM/Appium or requesting tests is not such a request; do not add guest build fallbacks or increase guest resources to make compilation fit.

## Project-owned runtime requirements

`test_requirements.py` validates portable platform requirements and prebuilt runtime inventory. `project_setup_hooks.py` owns bounded host preparation scopes; `run-setup-hooks.cjs.tpl` executes staged guest initialization scripts with private logs and no shell argument evaluation. Guest hooks are runtime-only: compilation still requires an explicit user exception. `guest_desktop.py` derives desktop initialization data from project requirements rather than storing dependency lists in VM hardware profiles. New guests record the requirements/script fingerprint privately; normal test execution rejects stale initialization.

Run `tests/test-desktop-provisioning.py` and `tests/test-project-setup-hooks.py` for declaration boundaries, seed setup, prebuilt inventory, hook failure/argument handling and fingerprint invalidation. `tests/test-work-guests.py` covers the small binary-free cloud-init document and bounded readiness probes. The optional Windows display helper is compiled by the host preparation tool and only loaded in the guest; never replace it with guest `Add-Type -TypeDefinition`.

## Config-driven test proxy

`run-test-env.sh` is the unified host entry point. Its `--profile` branch retains the original backend environment/lease/metrics implementation; `--config` delegates to the Python environment owner, which enables only declared adapters. The legacy script is an exec-only alias. The Windows/Linux JVM Appium relay mirrors configured file roles. Linux rewrites launch capabilities and quoted JVM argument files to the target JDK and POSIX artifact paths; other WebDriver traffic is unchanged. Test methods do not perform SSH or staging. Session creation uploads current classpath/JDK/agent artifacts and per-case inputs. Output collection precedes session responses and diagnostics. Guest private state is retained across driver restart and removed only under configured descendant roots at run exit. A per-guest test lease serializes desktop use. Host commands use the shared scoped process-group/Windows Job Object runtime, bundled by scripts/sync-process-runtime.py; no guest build commands are supported.

Run tests/test-test-environment-ownership.py for shell-free forward acknowledgement, failed session handoff rollback and diagnostic/delete ownership boundaries. Forwarding uses `ssh -N -T` with null stdin and waits for the local listener / remote forward acknowledgements in private OpenSSH startup diagnostics. Never keep a guest PowerShell blocked in `Console.In.ReadToEnd`: Windows OpenSSH can leave it behind after disconnect, exhausting guest commit memory over repeated runs. A confirmed Appium delete releases session ownership even if later diagnostics fail; unconfirmed rollback retains it for cleanup.

Run tests/test-linux-transport.py for POSIX classpath/file mapping, prebuilt archive contents, credential rejection, cleanup boundaries and transformed WebDriver handoff. Linux operators supply TEST_ENV_LINUX_RUNTIME as described in README.md; the host owns all Gradle/test execution and builds, while the prepared guest Appium desktop runs only the application.

Run tests/test-test-environment.py for environment validation, argv/exit status, lease contention, service forwarding roles, restart-state retention and protocol passthrough. Keep the Docker shell/lifecycle tests against the new entry point. Existing package/provisioning and status checks remain independent. Real acceptance uses project-owned environment configs and host builds; no application fixtures belong in this plugin.

Unconfirmed process-tree/session cleanup retains the per-guest test-environment.lock with phase cleanup-uncertain. Inspect the recorded native owner and guest Appium state before operator recovery; never steal or automatically discard that lease.

Project integration keeps provider setup outside consuming repositories. Operator-owned `TEST_ENV_DOCKER_PROFILE` and `TEST_ENV_GUEST_PROFILE` fill omitted connections; `launch.artifacts` names JVM properties containing additional prebuilt files. Appium diagnostic extensions execute beside the application and return text through WebDriver without provider-specific client flags.

macOS first boot enables dedicated-account automatic login using an authenticated, atomic root-only kcpassword file and loginwindow preferences, refuses FileVault-enabled setups, and verifies the loginwindow account before publishing readiness and rebooting. The Appium launcher is readable by the account; its LaunchAgent runs in the graphical user session. Acceptance requires that console user and a loaded gui-domain service, not only an open SSH port. Preparation uses a sparse image and hard-links the ISO when source/output share a filesystem to avoid unnecessary full-image copies. No work-guest compiler is involved.

Full createinstallmedia output must use GPTSPUD rather than the legacy Apple Partition Map layout. Attach the installer as a read-only USB disk and keep OpenCore as the bootloader. Hide the OpenCore self-entry using its documented `.contentVisibility` mechanism; otherwise the picker can repeatedly boot itself. Recovery can expose the installer under `/Volumes/Image Volume`, so validate the configured application path and empty target disk against the actual boot layout. Host OCR enlarges frames before strict shell-prompt matching (Pillow is pinned in requirements-guests.txt). Generated seed scripts always use LF, including on Windows. Interrupted pre-handoff UI state resets on a new QEMU process; the destructive handoff marker remains persistent. The live-panel validator accepts one graphical guest and reports switching/headless coverage only when supplied. Use QEMU_TEST_ACCEL=whpx for its native Windows screen regression when TCG is prohibited.

In the tested first-boot daemon, sysadminctl -autologin returned zero while reporting SACSetAutoLoginPassword error:22 and leaving /etc/kcpassword absent. It requires a console SessionAgent, so it is not the unattended credential publisher. The Node helper authenticates the generated account, writes loginwindow-compatible NUL-terminated/padded credentials atomically with mode 0600, clears the installer’s oneTimeAutoLogin flag, sets the account/unlocked preferences and erases the temporary plaintext file. Leaving that installer flag enabled makes loginwindow remove autoLoginUser and kcpassword after its first login, so a successful first boot alone is insufficient; verify automatic login survives the bootstrap reboot. Microsoft's [macOS user resource](https://github.com/microsoft/macos-cookbook/blob/master/resources/macos_user.rb) uses the same root-only loginwindow credential contract. Actual GUI-session/Appium acceptance remains mandatory.

For unattended Recovery disk selection, prefer macos.target_disk=serial:work-target with the same serial on the QEMU target device. The bounded IORegistry parser selects exactly one whole BSD disk under that serial; zero/multiple matches fail before erase. The existing whole-disk and nonempty-partition checks still apply. Legacy /dev/diskN selectors remain explicit but require stable enumeration. Parser tests cover reordered/foreign disks, ATA serial padding and missing/ambiguous targets.

The default QEMU USB keyboard is identified by product 1/vendor 1575/country 0. First boot adds only its ANSI entry (1-1575-0 = 40) to com.apple.keyboardtype, preserving other device entries. This avoids the Keyboard Setup Assistant on the unattended test desktop; it does not globally suppress keyboard detection or change physical host keyboards.

Appium startup probes Git for optional revision metadata. On stock macOS, /usr/bin/git is an install-on-demand developer-tools shim. The launcher checks xcode-select --print-path without invoking Git; if no toolchain is selected and DEVELOPER_DIR is unset, it uses the conventional CommandLineTools path so the shim returns a missing-tool error instead of opening an installer. Explicit operator toolchains are preserved. No developer tools are installed or compiled by this handling.

Live acceptance: Intel macOS Sonoma 14.8.9 (23J631) completed a blank-disk unattended installation with the experimental WHPX CPUID-cache runtime, four vCPUs and 4096 MiB RAM. The bootstrap reboot automatically entered the test account; SSH and the GUI-session Appium 3.2.2 server passed. Additional warm reboots retained the same native QEMU process and restored automatic login/Appium. Keyboard-type and missing-Git-shim initialization were also exercised on the installed guest. A real browser verified the source status panel card and captured guest desktop frame with no browser errors while the Alpine backend stayed stopped. This run exercised one graphical guest, not multi-guest switching, and Appium server readiness, not a macOS application UI test or driver session. No work-guest compilation was performed.

The Windows guest transport sends PowerShell scripts through OpenSSH stdin command mode, with ASCII/base64 framing for UTF-8 script content. The remote command stays bounded even as full-suite staging/cleanup paths grow; cmd.exe argument limits must not truncate scripts. The wrapper preserves terminating PowerShell errors and native command exit codes. A live guest probe covers a 20,000-character Unicode script; transport regression tests cover bounded arguments and private failure diagnostics.


A subsequent macOS toolchain check installed Apple-signed Xcode 16.2 (16C5032a), selected its developer directory, accepted the license and completed first-launch installation. With an explicit guest-build exception, WebDriverAgentMac from Mac2 4.5.0 built successfully on the four-vCPU WHPX guest without enlarging its resources. The runner and Xcode Helper received Accessibility permission through the guest UI, and automation mode was enabled with Apple's tool. Host-connected Appium created a Finder session, returned native XML and a PNG screenshot, clicked File / New Finder Window and verified the resulting window, then deleted the session. This establishes a native Mac2 UI smoke test; consuming-project end-to-end acceptance is separate. The general no-guest-compilation rule remains unchanged.


The tested macOS VMware SVGA framebuffer initially exposed only 1280×800. Selecting `1920x1080` in a separate private OpenCore `UEFI/Output/Resolution` configuration produced a 1920×1080 guest mode and QMP frame after restart, with four vCPUs, 4096 MiB RAM and WHPX unchanged. Preserve firmware originals and verify the actual mode rather than assuming a window-resize request enlarges the desktop. Guest SSH may close before macOS finishes shutting down; a forced QEMU stop at that point can produce the abnormal-shutdown warning at the next login.

Ubuntu console acceptance requires an actual XFCE session for the configured test user. Keep the isolated Xvfb test session on display :99: automatic display allocation can claim :0 before LightDM starts and prevent console login. Configure both LightDM user-session and autologin-session as xfce; installing XFCE alone does not replace an unavailable default ubuntu session.

## Runtime and session failure boundaries

The relay models creation as IDLE, REQUESTING and UNKNOWN. Only a parseable success with a nonempty string session ID publishes session ownership. Transport/parse failures after dispatch enter UNKNOWN; interrupted dispatch remains REQUESTING. Closing either unresolved state raises CleanupUncertain before local input cleanup, so the environment owner retains its lease even when the HTTP handler has converted the original error into a 502 response. Do not infer remote rollback from a disconnected client or enumerate/delete arbitrary upstream sessions.

Runtime preflight compares platform and arch against the selected guest OS and the supported x64 target before disk creation. This also applies without project requirements; preparation checks its base before host hooks. Legacy runtime archives missing arch are rejected for new installations/preparation. Existing run paths retain their recorded configuration and do not revalidate the old archive; test this with a mocked supervisor and unchanged disk/record/archive bytes, never with a real VM restart. Fixtures must be actual runtime ZIPs with target metadata rather than arbitrary bytes.

For guest hooks, fingerprint v2 appends a structured ordered list of original script identifiers and per-file SHA-256 values. Resolved host checkout paths are excluded. No-guest-hook fingerprints remain the requirements file SHA-256 for compatibility. Never rewrite an existing VM's stored fingerprint to bypass reinitialization.

The ownership suite covers a real loopback HTTP disconnect after simulated remote creation, malformed success bodies, missing/invalid IDs, interrupted requests, lease retention, pre-dispatch failure and confirmed cleanup. Hook tests cover content redistribution and checkout-independent fingerprints. Provisioning tests exercise OS/architecture mismatches and assert that no disk command or host hook executes on preflight failure. These tests use temporary directories and local fake servers; do not start or repair an operator VM to run them.

The native multi-QEMU smoke in test-work-guests.py is opt-in: set QEMU_TEST_ACCEL explicitly only when native process startup is authorized (WHPX on Windows, KVM on Linux). With the variable unset, it skips without launching QEMU. There is no default TCG choice. Run this optional smoke serially because it currently uses fixed forwarding ports; default source/client failure-path checks need no VM startup.

## Structural ownership and initialization snapshots

TestEnvironmentOwner owns every configured execution mode through one private ExitStack: host process trees plus any temporary workspace, SSH transport and Appium relay. Construct it without a home for local/Docker-only execution; acquire_lease(home) attaches one optional guest reservation before guest resources are acquired. The home constructor remains a convenience for direct scoped guest use. OwnerState models execution lifecycle independently of whether a guest lease exists. Failed lease acquisition never claims a foreign reservation; a second acquisition cannot replace an owned reservation. Register guest resources through owner.callback / owner.enter_context. Register the host CommandTree.stop callback before launch, so the owner observes incoming cancellation before any process-tree cleanup can replace it. Each failed cleanup, including interruption, sets RETAINED in memory and persists cleanup-uncertain before the next cleanup runs. Retention is sticky: subsequent exceptions or context-manager suppression cannot make it releasable. Failed retention publication leaves the reservation intact and remaining cleanup is still attempted. Successful cleanup after an ordinary test failure releases the active lease; changed/foreign ownership is never overwritten or removed. CleanupUncertain belongs to this owner module; the proxy reports uncertainty through that shared contract rather than owning the lease. Do not infer retention solely from the final exception or scan exception chains to reconstruct lost ownership state.

Configured test execution uses one CancellationRequest shared by CliSignalScope, TestEnvironmentOwner and transports. Only the main thread may commit the frozen CancellationState, accept cancellation, consume worker events, publish the terminal result or mutate lease state. Signals only enqueue immutable request events through CPython's reentrant SimpleQueue; they acquire no worker lock and raise no exception. Workers enqueue observations and cleanup failures, then read one state snapshot at a checkpoint. They never construct or replace the shared cancellation. Context-local cleanup shields protect the main cleanup context without disabling an existing HTTP worker's checkpoint.

The main thread consumes finite queue prefixes bounded by a fence. begin_cleanup inserts an acceptance fence, closes admission and enters DRAINING: requests before the fence remain eligible, later signal requests cannot change the outcome. Preserve an already accepted cancellation first. Otherwise an incoming primary execution interruption takes priority over queued, uncommitted worker observations; consume worker observations in queue order, then accept the first eligible signal request if no interruption has been accepted. This priority is a main-thread decision, not a race between worker assignments. Existing workers continue responding to the accepted cancellation during DRAINING. FINISHED freezes cancellation; late observations cannot replace it.

Resource-using HTTP dispatches register a worker scope under the relay lock; nested SSH/SCP/forward/stop operations share that scope. Each scope publishes observations and failures before decrementing its completion count and releasing the relay lock. HTTP error conversion happens after publication. Dispatch control interruptions return a fixed HTTP error instead of escaping as raw worker tracebacks. Closing the relay rejects new work before shutdown and drains the resource-using dispatch. Late request-body readers cannot enter resource work after admission closes. At the final boundary, seal_workers closes admission, confirms the resource-worker count is zero and collects the final event prefix before any lease release. An unconfirmed worker drain retains the lease and reports uncertainty; it cannot authorize success or lock release.

Cleanup failures have a sticky event ledger independent of exception propagation and HTTP responses. Every attempted transport child stop reports failure at its resource boundary. A later successful retry does not erase it. Main-thread owner checkpoints, callback-finally boundaries and final sealing collect these reports into the owner's cleanup_failures, persist retention and continue draining all callbacks. Failure to publish retention leaves the reservation intact, records the publication error and preserves the original cancellation. Only TestEnvironmentOwner may create, retain or release a guest lease; worker attempts to mutate owner/CLI state are rejected before I/O. Context suppression cannot swallow cancellation or authorize releasing uncertain ownership. Release is a positive commit after all callbacks, confirmed worker completion and final event collection. EnvironmentCleanupError.failures preserves the original failures and nested transport aggregates as the cancellation cause.

Within configured execution, defer_cancellation and the TestCommandTree adapter shield checkpoints without installing or replaying signal handlers. Registration completes before the next checkpoint. The adapter reuses the canonical Windows/POSIX process-tree backends without changing their shared runtime. Outside this execution context, existing VM-management commands retain their legacy signal-deferral contract; this refactor does not change VM lifecycle commands. Direct legacy owner/transport callers remain bounded by their existing waits. Do not use a cooperative owner without its CLI signal context when expecting OS-signal recording.

test_environment.run uses the same owner in local, Docker-only and guest modes. main includes configuration loading in one CliSignalScope.execute operation. Checkpoints run before guest acquisition, after transport/forward/readiness registration and before process launch. CommandTree.stop is registered before start. The host command uses wait(timeout=.1) between checkpoints, never a second launch. The readiness HTTP request retains its 10-second timeout and is checked on both sides. Register the Appium relay before starting its thread; close handles an unstarted server without shutdown/join and rejects new work before waiting for active workers. Cleanup never adds a checkpoint that could abandon an already owned resource.

GuestTransport captures the same request for HTTP workers as well as the main thread. Configured SSH/SCP calls use one owned Popen and communicate in at most .1-second slices while retaining the original total operation timeout. Input is sent only on the first communicate call. Forward readiness checks cancellation between .1-second waits. Short-lived children are registered before checking cancellation and are stopped before returning, including constructor preflight calls. Successful stops remove their handles; uncertain stops leave handles owned and raise TransportCleanupError (a CleanupUncertain aggregate). Capture original interruption before a stop error can replace it. close attempts every remaining child in reverse order and reports all failures. The environment owner alone decides whether the guest lease can be released. Legacy calls outside configured execution keep their existing subprocess.run behavior.

CliSignalScope captures one frozen CliSuccess/CliFailure and rejects a second invocation. It has no execution-frame scan, publication mask, signal replay or handoff retry. main leaves the execution exception handler before finalization. CliResult snapshots the exit status and a frozen CleanupReport once; later output reads only that result, not mutable ownership or exception chains. Reports contain fixed categories/counts and the committed acquired-lease state, never exception messages, custom type names, paths, command arguments or credentials. Confirmed clean execution preserves the host exit code. Accepted cancellation preserves its original exit code even when cleanup fails; ordinary cleanup failure returns 1. An acquired, unconfirmed lease prints the retained-lock recovery hint; local/Docker-only runs never invent a guest lease. Closed/broken stderr cannot change the status. Publish previous signal handlers before installation for rollback; restore in reverse order with SIGINT last and finish an interrupted restoration. Context-local cancellation is restored on normal exit and failures.

Run the isolated regressions with QEMU_TEST_ACCEL unset:

```bash
python3 tests/test-cancellation.py
python3 tests/test-worker-protocol.py
python3 tests/test-environment-cli.py
python3 tests/test-environment-owner.py
python3 tests/test-transport-cleanup.py
python3 tests/test-test-environment-ownership.py
```

Existing regression assertions are retained. These suites cover record-only handlers, nested handoffs without handler replacement, request-before-start and request-during-wait, all execution modes, repeated signals at capture/bytecode boundaries, original cancellation identity and exit codes, immutable terminal snapshots, cleanup suppression, partial startup, child aggregation, foreign/retained locks, private diagnostics, closed output and handler restoration. The worker-protocol suite adds deterministic checkpoint/commit races, main-only state and lease mutation, cancellation priority, concurrent failure producers, request-acceptance fences, nested worker completion, rejected late work, unconfirmed-worker retention, failed retention publication and fixed HTTP interruption responses. A real loopback HTTP test converts a worker stop failure to 502, then succeeds on the final stop retry; both ordinary-failure and cancellation cases must retain the lease, original status and redacted io count despite repeated cleanup-time signals. All metadata writes in that path are asserted to run on the main thread. Adapters are mocked or local fake HTTP servers. Two tests use only owned host Python fixture processes for process-tree cancellation and stdin delivery. No VM, SSH server or guest service is contacted.

InitializationSnapshot captures the original requirements bytes, detached record JSON, staged hook manifest JSON and an immutable tuple of script names/bytes. capture reads the requirements once for both parsing and hashing and reads each selected script once. apply attaches the snapshot to an installation config; record_for selects its detached metadata for preflight and persistence. Seed payload, cloud-init packages and dimensions all derive from that same snapshot; no script pathname is re-read during packaging. load remains a detached record-view API for existing callers. Persisted records contain metadata/fingerprint only, never the in-memory snapshot object or its script bodies. A legacy record with guest hooks cannot generate a new seed without a captured snapshot. Normal existing-VM run paths retain their stored records and do not rebuild seeds.

The snapshot retains the fingerprint v2 byte layout, including its no-hook compatibility rule. Source-file changes after capture affect later captures and future freshness checks, never the contents of a seed already being assembled. Do not patch stored VM fingerprints or reset disks to accommodate source changes.

Run tests/test-environment-owner.py for compounded proxy/transport failures through the actual environment.run wiring, context cleanup errors, interrupted teardown, retention-publication failure, foreign ownership and successful release. Run tests/test-initialization-snapshot.py for source mutation/deletion, one-read capture, detached-view mutation, Ubuntu/Windows payloads, cloud-init configuration and actual persisted-record/seed agreement. These suites use temporary directories and mocks/local fixtures only. Keep QEMU_TEST_ACCEL unset for normal regressions; native smoke remains an explicit separate opt-in.

The relay switches to CLOSED before server shutdown or waiting for its session lock, then drains the active worker under that lock before cleaning launch resources. A previously accepted HTTP worker that finishes reading its body after close must reject the request before staging files or contacting upstream. The ownership suite verifies this with a real loopback connection held at the request-body boundary; no VM or application is launched.

## Bundled Windows macOS GPU dependencies

`patches/reims-windows/sources.json` pins the three public source revisions and
their patch hashes. The patches preserve the tested local Windows port: Reims
platform memory and C API, metal2vulkan runtime host-memory support, and QEMU's
WHPX/section-backed RAM integration. `reims_sources.py` captures the lock,
patches and build templates before checkout; it only applies them in a fresh
cache workspace. Never point this preparer at a contributor's existing checkout.
The Reims QEMU gitlink is deliberately excluded from its patch; QEMU is fetched
and patched independently from the same lock.
The plugin's `.gitattributes` keeps checksummed patch/driver files and GPU build
templates at LF, and marks the kext binary as non-text. A temporary repository
checkout with `core.autocrlf=true` preserved all 16 release inputs byte-for-byte;
retain these attributes when updating or distributing the bundle.
Whitespace exceptions for these three patch files preserve unified-diff context
prefixes before Makefile tabs and blank final context lines; ordinary source
files retain their normal whitespace checks. Do not normalize the patch bytes.

Tracking: [Windows support #17](https://github.com/steelbrain/reims-vgpu/issues/17)
and [merged early port #57](https://github.com/steelbrain/reims-vgpu/pull/57)
refer to the earlier architecture, not this patch set.
[Memory issue #71](https://github.com/steelbrain/reims-vgpu/issues/71) describes
related aliasing/import failures. [QEMU #12](https://github.com/steelbrain/qemu-reims-vgpu/pull/12)
contains related section backing but was closed without merging;
[QEMU #4](https://github.com/steelbrain/qemu-reims-vgpu/pull/4) tracks other WHPX
fixes. No matching metal2vulkan Windows-runtime or detailed-timing issue was
found in the review. Retire a patch only after its behavior is present in a
reviewed upstream pin and clean-build plus native GPU acceptance passes.

`reims_runtime.py` builds the static library and EFI ROM, obtains Rust's native
link dependencies, renders pkg-config metadata and builds QEMU with WHPX only.
It reuses the existing PE DLL bundler and runtime-file/accelerator verification.
Publication includes the immutable recipe and upstream license texts. A failed
or interrupted build preserves its source/output evidence; cancellation retains
its build reservation. The separate runtime selection must not alter Windows
guest defaults or silently fall back to TCG.

`drivers/pvg-timing-fix` contains the independent timing hook, the qualified
prebuilt x86-64 kext, checksum manifest and dependency license. To rebuild it,
prepare clean checkouts of [Lilu](https://github.com/acidanthera/Lilu) and
[MacKernelSDK](https://github.com/acidanthera/MacKernelSDK) at the revisions in
`artifact.json`, then run its `build.py --lilu-source ... --kernel-sdk ...
--output ... --clang <LLVM-23-clang++>` on the designated preparation machine.
Windows produces Mach-O objects and retained LLVM IR; final linking uses
`xcrun ld -arch x86_64 -kext -undefined dynamic_lookup` with those two objects
on a designated macOS build machine (`--link` does this locally on macOS).
This is not permission to build in a work guest. Review the kext imports and
type, update the artifact manifest deliberately, and requalify before replacing
the bundled binary. The exact byte guard must be reviewed for every new guest
kernel build; do not weaken it to accept an untested release.

EFI preparation captures each verified driver file once in an immutable
`DriverSnapshot`; Lilu checksum verification and ZIP extraction consume one
captured archive buffer. Image writes and receipt hashes use those bytes,
with driver readback before completion. The output image and sidecar receipt
are created exclusively, and receipt/source aliases are rejected before any
output creation. Failed attempts preserve newly created partial outputs.

Run `python tests/test-reims-runtime.py` after installing
`scripts/requirements-guests.txt`. It exercises patch checksums and capture,
real Git patch application in synthetic repositories, runtime selection and
environment isolation, unsupported builds and real FAT-image preservation.
Native validation additionally requires a clean public-source build, verified
artifact/DLL manifest, a separate VM using the generated firmware, nominal
CoreVideo timing, visible Metal presents and unchanged application acceptance.
Do not treat packaged source or an accelerator list as a live GPU test.

On 2026-10-26, a fresh checkout/build using only these public pins and bundled
patches passed runtime/DLL verification. An isolated copy of a previously
blank-disk-installed 24H32 system used that runtime and an EFI image generated
by the bundled preparer, with four vCPUs and 4096 MiB RAM. Two normal in-guest
shutdown/cold-start cycles, native desktop reconciliation and subsequent
read-only verification passed. Eight immediate/timed Metal frames matched
their framebuffer colors; 1800 CoreVideo samples had no target/clock deviations
over 100 ms. The unchanged external business suite passed all 18 tests with
zero failures, errors or skips through the operator-owned Mac2 adapter, with
confirmed session/forward cleanup. Generated Codex package regressions, runtime
verification and a subsequent native desktop check also passed.
This qualifies the opt-in `reims-whpx` path,
not an arbitrary host GPU, macOS release or the default Windows guest runtime.

A separate copy stalled after an ACPI power-button request raced an SSH
shutdown. It was paused with its memory, disk and ownership evidence retained;
the root cause is not established. The successful cold-start qualification
used one normal in-guest shutdown request and confirmed native exit before
relaunching. Do not claim that ACPI shutdown or sleep/resume has been qualified.

## Prepared Intel macOS desktop recovery

Sequoia's loginwindow checks a separate `/var/db/.AppleSetupTermsOfService`
cookie before ordinary setup completion. A diagnostic macOS 15.8.1 boot retained
that cookie after `startosinstall --agreetolicense`; its log reported `Setup launch
reason: terms and conditions` despite a valid account, `.AppleSetupDone` and
automatic-login configuration. Clearing the cookie and rebooting restored the
desktop and authenticated SSH. The bootstrap now clears it before its final
reboot, matching the [Setup Manager deployment finding](https://github.com/jamf/Setup-Manager/discussions/96).
That diagnostic repair alone does not establish a clean unattended installation.
The package postinstall rearms first boot only when explicitly installed on the
running target, allowing an upgrade package to refresh the reviewed existing
account's configuration without changing its password.

`macos_desktop_plan.py` captures a private manifest, its credential and setup
script bytes before guest mutation. Checksum-pinned archives stream through SCP;
the guest checksum is checked before the supplied setup script executes. Require
existing pinned SSH host keys and verified supervisor/QEMU/listener identity.
`macos_native.py` owns specific W3C sessions and the newly created Finder window;
`macos_permissions.py` selects unambiguous visible System Settings controls and
verifies every transition. `macos_console.py` supplies physical QMP input and
recognizes only the explicit system authorization dialog for credential entry.
Unknown layouts, OS builds, signing identities or unsupported key characters fail.

The test account's ByHost screen-saver idle time is set to zero during first
boot and desktop preparation. `pmset displaysleep 0` alone did not prevent a
cloned test desktop from reaching its lock screen while SSH and Appium remained
ready. Qualification checks `IOConsoleLocked` and the matching on-console
session before creating any native client. A cloned lock cookie caused
loginwindow to restore a lock even after automatic login (`kLWLockFromCookieFile`);
idle-time configuration alone cannot clear that existing state. Reconciliation
verifies the matching on-console account and the secure-input PID's exact system
loginwindow executable, locates one visible `Enter Password` field beside the
known account label, rechecks the target after focusing it, then submits the
credential once through QMP. Allow up to two minutes for the cold-login state
transition; a qualified four-vCPU guest exceeded the previous 30-second wait
but subsequently reported unlocked without another password submission.
Actual unlocked IORegistry state is required before
native qualification. Unknown/ambiguous state or an unreviewed secure-input
process fails before typing. Verification never authenticates; password policy
and the OS-managed lock cookie remain untouched. Preserve uncertain ownership
from earlier failed tests.
The qualified login layout is English Sequoia at 1920x1080. Recognize the
account label and low-contrast placeholder in separate narrow crops; never use
the crop's assumed location as a blind password click. Tesseract TSV parsing
must disable CSV quote processing, since recognized quote characters are raw
text and otherwise consume subsequent rows. A target recheck immediately before
typing prevents a changed/unlocked console from receiving the credential.
System Settings authorization separately recognizes a unique password caption
and the complete authorization message. Its low-contrast placeholder/button
use separate crops of one captured 1920x1080 frame. Crop positions only constrain
OCR; input uses the recognized field bounds. After focusing, require the matching
unlocked console's secure-input PID to be a reviewed System Settings or SecurityAgent executable in the test account;
recheck the full prompt, PID, executable and process start time before typing
once. Missing AX fields do not permit blind input: the OCR field and secure-input
checks are mandatory for that path as well.

Finder element UUIDs can change when a new window changes the snapshot hierarchy.
`macos_windows.py` reads stable WindowServer window numbers through the built-in
JavaScript/Objective-C bridge and CoreGraphics, without Apple Events. It excludes
the desktop layer and window titles. Qualification matches only its newly created
window to native geometry, verifies the actual system geometry and disappearance,
and requires all pre-existing windows and their rectangles to remain unchanged.

The prepared WDA must be independent of Appium's driver-owned process lifecycle.
Its LaunchAgent runs test-without-building, and every new Mac2 session explicitly
uses webDriverAgentMacUrl. TestEnvironmentOwner owns reservations and tunnels.
Missing/malformed creation responses and failed specific deletion retain the
lease. Readiness is published only after resource cleanup and guest identity
revalidation; a competing lease must not overwrite an existing desktop receipt.

WDA caches Accessibility trust, so reconciliation starts with a fresh runner and
actual native qualification. Only an Accessibility failure triggers removal and
re-registration of reviewed grants; an enabled, working grant is left intact.
Revoking a valid grant while its runner caches trusted access can invalidate its
native snapshots. Qualification after repair therefore also uses a fresh runner.
`launchctl kickstart -k` only replaces the xcodebuild wrapper and can leave
testmanagerd's runner app listening on the same port. `macos_wda.py` unloads the
named job first, matches any remaining listener to a reviewed bundle executable,
account and process start time, sends TERM only after an immediate identity
recheck, confirms exit, then reloads the job. An unreviewed listener is never
signaled. Unconfirmed shutdown/restart retains ownership; no broad process-name
scan or kill is used. The readiness wait rejects the old listener PID.
If the guarded TERM fails, only a fresh confirmation that the original runner
is absent permits restart. A replacement or an unknown process probe still fails.

`TestEnvironmentOwner.on_drained` runs one terminal-metadata callback after all
registered resources and workers finish, before releasing its guest lease.
`DRAINED` forbids new owned resources. Desktop success and failure receipts use
this boundary; neither writes state after leaving the owner. Recheck lease
identity before publication, and retain ownership if publication fails. A
retained lease remains authoritative even if release fails after writing a receipt.

The review fixes were checked with deterministic input-replacement, output-path
collision, lease-publication and credential-target regressions. A native 24H32
authorization probe forced the OCR path, confirmed the secure-input identity
twice, submitted the credential once and reached the file picker without changing
existing grants. The public reconciliation command and real EFI-copy preparation
also passed. The full 18-case business result recorded above predates these
management fixes; it was not rerun for them.

Run `python tests/test-macos-desktop.py` for synthetic manifest, input, target
selection and session-ownership contracts. Keep native installation/cold-boot/UI
and consuming-project acceptance separate and record the selected release and
prepared asset hashes. This suite does not start a VM.

Run `node --test tests/test-prepare-runtime.cjs` for first-extension cache
creation and preservation/relocation of existing registrations. A server-only
archive legitimately lacks Appium's extension cache until first startup; the
offline preparer creates schema revision 4 when adding its first extension.

A clean Intel macOS 15.8.1 (24H32) run completed installation, automatic login,
prepared-runtime deployment, native Accessibility repair and two cold starts
without manual interaction, using four vCPUs and 4096 MiB RAM. The prepared
assets included Xcode 16.2 (16C5032a) and Mac2 4.5.0; no WDA or application
build ran in the guest. With a separately supplied experimental display runtime,
eight immediate/timed Metal frames matched the actual framebuffer colors and
1800 CoreVideo samples had no target/clock deviations over 100 ms. These GPU
results do not establish GPU support in the plugin's default managed runtime.
The unchanged external desktop business suite then passed all 18 tests with
zero failures, errors or skips through an operator-owned Mac2 launch adapter,
separate from the plugin's Windows/Ubuntu transparent JVM relay.
Guest sessions, application bundles and SSH
forwards were cleaned up before the complete lifecycle published acceptance;
the VM remained running and its test lease was released.

## Ubuntu VirGL/WHPX runtime

`scripts/virgl_runtime.py` builds the opt-in Ubuntu runtime without using private
experimental binaries. Its immutable snapshot captures the public QEMU and
VirGLrenderer pins from `patches/viogpu-windows/sources.json`, the checked patch
bytes, both WHPX patches and `templates/build-virgl-whpx.sh`. Mesa's Windows
guest driver is not built or installed for Ubuntu. The cache identity includes
these captured inputs; archives are privately copied and SHA-256 checked before
extraction. Changed recipes use independent cache directories. Busy/interrupted
builds retain their reservation until inspected. A complete runtime contains
recursive DLL dependencies, firmware, source licenses and the captured recipe.

For an explicit host preparation, use Python 3.12+ on Windows 11 x64:

```sh
python scripts/virgl_runtime.py --msys2-root C:/msys64 --jobs 8
```

Optional `--cache-dir`, `--qemu-archive` and `--virgl-archive` select private
storage and already downloaded pinned archives. Set `QEMU_VIRGL_CACHE` when
profile startup must use an alternate cache, including home paths with spaces;
use the same cache for explicit builds and guest commands. MSYS2 installs the required
UCRT64 compiler, Meson, Ninja, SDL2 and libepoxy packages. No system QEMU is
replaced. Verification requires WHPX only, the VirGL device, hidden SDL option,
and matching hashes for every bundled file. Accelerator/device enumeration does
not prove actual GPU rendering.

`guest_seed.py` chooses the display setup fragment inside the shared desktop
session template. The GPU fragment inherits LightDM's DISPLAY/XAUTHORITY;
the default fragment still owns Xvfb/Openbox. GPU autostart uses a private
D-Bus session and the existing temporary unlocked keyring. `guest_gpu.py` rejects
software renderers and mismatched dimensions, then publishes a boot ID and
session PID/start-time receipt. Acceptance checks that live receipt and the
existing Java, desktop and Appium requirements. The installation record includes
the GPU backend, preventing a profile-only change from adopting a software disk.
Initial acceptance still requires completed cloud-init. After recorded successful
installation, cold starts retain desktop checks without requiring the one-time
NoCloud seed to remain attached.

Run the isolated regressions without starting any VM:

```sh
python tests/test-virgl-runtime.py
python tests/test-desktop-provisioning.py
python tests/test-whpx-runtime.py
python tests/test-guest-panel.py
python tests/test-work-guests.py
```

Native qualification must use a fresh state directory, the built managed runtime
and the unchanged consuming project's runtime requirements. Require hardware
renderer output, actual rendered color readback, native Appium source/input and
screenshots, followed by a normal shutdown/cold start and the unchanged business
suite. Keep logs, media, profiles and account data private. Native Appium
screenshot support remains the responsibility of the project's normal driver.

`patches/qemu-11.1.2-sdl-gl-snapshot.patch` adds an optional SDL GL snapshot
callback to QMP screendump when the console has no CPU surface. It reads the
current scanout on the main thread into an owned pixman image before PNG encoding
can yield. Readback is on demand, with crop/orientation conversion and restoration
of SDL context, read framebuffer/buffer and pixel-pack state. Failed reads never
publish an image. Existing CPU-surface capture keeps its original path. The patch
is captured in the recipe, so older runtimes are not reused for panel capture.

On a logged-on Windows desktop, exercise the helper from the actual patched
QEMU source tree without starting a VM:

```sh
python scripts/test-qmp-snapshot-native.py --qemu-source /private/build/qemu-11.1.2 --output /private/native-snapshot
```

The native regression checks 40 cases across orientations, crops, sizes, padded
rows and bound pixel-pack buffers, plus GL failures and recovery. It also mutates
pack-state normalization as a negative control and requires the regression to
detect it. VM qualification must compare actual QMP PNGs with native screenshots,
exercise pause/resume and display resize, and continuously capture through the
registered screen tool during unchanged business tests. Restore the display mode
and resume the guest in cleanup before releasing the test lease.

## Experimental viogpu source bundle

`patches/viogpu-windows/sources.json` locks source revisions/archive hashes,
patch bytes, and before/after hashes for every modified file. Sources are QEMU
11.1.2, VirGLrenderer 1.3.0, and the pinned `arehnman/virtio-win-mesa` revision.
The VirGL patch includes the two MSYS2 1.3.0 build compatibility changes
(`void` prototype and conditional `sys/ioccom.h` include), then the functional
readback fixes. Preserve upstream license notices when distributing builds;
no third-party binary, private profile, raw application log or credential is bundled.

### Prepare and verify

Download the archives named in the lock and verify SHA-256 before extraction.
Use fresh LF source checkouts; never patch an operator's working checkout.
The verifier checks captured bytes in temporary directories and never changes
its supplied source paths:

```sh
python plugins/qemu-guests/scripts/verify-viogpu-bundle.py \
  --qemu-source /private/src/qemu-11.1.2 \
  --virglrenderer-source /private/src/virglrenderer-1.3.0 \
  --mesa-source /private/src/virtio-win-mesa
```

Without source arguments it verifies bundle integrity only, not applicability.
After verification, use `git apply` with the corresponding bundle patch inside
each fresh source tree. QEMU also needs the existing plugin-owned WHPX partition
reset and CET/XSAVE patches; this GPU patch changes separate files. The hidden
switch must set SDL_WINDOW_HIDDEN before window creation. Device reset only marks
pending work on the vCPU thread; scanout/GL cleanup belongs to the main loop.

In an MSYS2 UCRT64 host shell, with GCC, Meson, Ninja, pkgconf, Python/PyYAML,
libepoxy and SDL2 installed, build the patched renderer:

```sh
meson setup /private/build/virgl /private/src/virglrenderer-1.3.0 --buildtype=release --wrap-mode=nodownload
meson compile -C /private/build/virgl
```

Build QEMU using the existing WHPX host recipe, adding `--enable-sdl`,
`--enable-opengl` and `--enable-virglrenderer` and linking the patched renderer.
Keep `--disable-tcg`. Bundle the resulting executable, DLL dependencies and
firmware into a separate private runtime; never overwrite system QEMU.
Build the guest Mesa DLL on the host with MSVC, Windows SDK/WDK and Meson:
`-Dgallium-drivers=virgl -Dgallium-d3d10umd=true -Dgallium-wgl-dll-name=viogpu_wgl
-Dgallium-d3d10-dll-name=viogpu_d3d10 -Db_vscrt=mt -Dllvm=disabled
-Dvulkan-drivers=[] -Dvideo-codecs=[] --buildtype=debugoptimized`.
These are host build prerequisites, not packages to install in a test VM.

### Ownership and regression contracts

The guest clear operation owns its view independently of framebuffer binding:
borrow a matching bound handle, otherwise create/clear/delete a temporary surface.
The readback adapter owns layer iteration and guest offsets. Each layer worker
owns a packed temporary buffer; only valid pixels undergo conversion, then scatter
to guest row/layer strides. D24S8 and Z24X8 use integer bit transformations.
This adds a per-layer allocation/copy; throughput has not been benchmarked.
A failed GL read must return an error before conversion/publication. Restore read
and draw framebuffer bindings. Select the alternate texture path by capability,
not as a retry after failure. Multisample resources require an explicit resolve.
Earlier successfully published layers are not rolled back if a later layer fails.

Run static integrity/failure tests without starting a VM:

```sh
python plugins/qemu-guests/tests/test-viogpu-bundle.py
```

Run native graphics regressions on a logged-on Windows host. Keep UCRT64 DLLs
and the compiler on PATH. The output directory must be new:

```sh
python plugins/qemu-guests/scripts/test-viogpu-native.py \
  --virgl-source /private/src/virglrenderer-1.3.0 \
  --virgl-build /private/build/virgl --output /private/results/viogpu
```

This builds tests on the host and creates hidden SDL windows. It exercises 24
exact readbacks (D24S8/Z24X8/RGBA8, mips, multiple layers, split iovecs, offsets,
row/layer padding and unchanged upload source), five read-error/recovery checks,
and D3D clear isolation on WARP. Z24X8 includes zero, one, 255, 256 and the two
largest depth values. Clear isolation checks all eight subresources after each
of eleven clears, including partial arrays and independent depth/stencil clears.
A negative control widens a clear and must report 144 mismatches with exit 1.
`results.json` identifies the tested DLL; failure retains build and case logs.

For guest hardware acceptance, stage only the prebuilt `clear-isolation.exe`,
run it in the dedicated interactive test session with a private log path, and
repeat with `warp`. Preserve exit codes and fresh logs. Keep guest driver registry
entries as a multi-string with the original entry count and absolute paths.
Back up the original registry values and DLL before selecting a distinct patched
DLL name. Do not replace a loaded host DLL: gracefully stop only the owned VM,
replace its private runtime file, record the hash and cold-start it. Rollback uses
the same stop/restore/start sequence and the original guest registry snapshot.

If a Java test app loads system EGL/GLES libraries instead of its packaged ANGLE,
use a test-launch-scoped empty `java.library.path` and confirm actual loaded modules.
Do not impose that workaround on all Java processes or all consuming projects.
Use the normal runner-owned temporary Appium connection; no persistent tunnel
service is part of this bundle.

### Qualification limits

The clean bundled VirGL source was rebuilt and passed the native regressions.
The equivalent experimental runtime passed guest hardware/WARP clears and two
representative consuming-project desktop E2E cases with screenshots. An earlier
renderer passed a full 18-case suite and warm reboot recovery; those results do
not qualify the latest DLL. Hidden startup and main-thread reset were verified
in the experiment. Clean-source QEMU/Mesa patch application is verified here;
they were built in the experiment, not rebuilt as part of this packaging check.

This is Windows x64 native OpenGL, with guest D3D feature level 10.0 / ANGLE ES2.
It does not qualify GLES, all formats, host logout/session 0, host boot autostart,
fresh-image unattended GPU installation, or long-term reliability. A separate
pre-existing default-window OpenGL readback issue remains outside this bundle.
Keep consuming-project acceptance artifacts private and rerun the full suite,
screenshots and warm recovery when qualifying a newly built complete runtime.
