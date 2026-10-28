# Development

## Report sharing controllers

`diff-sharing` and `test-report-sharing` use Python 3.10+ standard-library
controllers. Same-named `.py` entrypoints own argument parsing, report generation,
collection, and loopback/tunnel lifetime; `.sh` files only select an interpreter
and forward arguments. Public tunnels still require ngrok and credentials.

The canonical shared runtime is `scripts/report-sharing/report_runtime.py`.
After changing it, run `python scripts/sync-report-runtime.py` to bundle identical
copies in both independently installed plugins. `--check` verifies those copies.
Keep maintained page bodies under each plugin's `templates/` directory.

Run the thin shell compatibility suites in both plugins,
`python tests/test-report-python.py`, `python tests/test-report-snapshots.py`,
`python tests/test-report-launchers.py`, and `python tests/test-validation-workflow.py`.
Install the browser with `uv run --with playwright==1.62.0 playwright install --with-deps chromium`,
then run `uv run --script tests/test-report-browser.py`. On Windows, put Git Bash
on PATH, or set `BASH_TEST_BINARY` to its absolute executable path for the Shell
dispatch contracts (Windows CI does this to avoid the WSL `bash.exe` shim).
`PLAYWRIGHT_CHROMIUM_EXECUTABLE` can select an already installed Chromium.
Browser tests use generated local snapshots and a deterministic Difftastic CLI
fixture, not a live Difftastic installation or public tunnel. Each browser contract
has a separate unittest result. No shared devices or existing report servers are used.

Report test coverage ownership:

| Contract | Suite |
| --- | --- |
| JSON summaries, bounded scanning, duplicate XML contents, HTML deduplication, directory aliases, empty reports, URL encoding and escaped labels | `tests/test-report-python.py` (including `report_contracts.py`) |
| Difftastic configuration/payload, unavailable/failed status, Git statistics, committed/worktree modes and submodule exclusion | `tests/test-report-python.py` |
| Actual rendered fragments/context, safe special characters, renderer/layout switching and Git fallback | `tests/test-report-browser.py` |
| Atomic publication failures, overlapping snapshots and immutable linked assets | `tests/test-report-snapshots.py` |
| Loopback/tunnel lifetime and cancellation | `tests/test-report-launchers.py` |
| Shell target script, exact argument boundaries and exit-status propagation | `tests/test-report-python.py` (`ShellContracts`, recording interpreter fixture) |
| Shell help, invalid arguments and interpreter selection | Plugin `tests/test-*.sh` suites |

Native and browser suites share `tests/report_test_support.py` fixtures. Source
string assertions are restricted to explicit template ownership constraints;
interaction assertions execute in Chromium. The coverage checker discovers all
`tests/test-report-*.py` entrypoints and requires CI wiring. Keep new contracts
independently named rather than accumulating unrelated operations in one test.

Native tests cover bounded scans, custom project directories, overlapping roots,
recursive output rejection, URL/HTML escaping, binary Git statistics, committed
comparisons, and invalid input. Argument parsing returns explicit project/output paths without changing global cwd.
Git queries use an explicit repository cwd, and report scans resolve their roots
against `--project-dir` (default: caller cwd). Cache identity uses that project.

Submodule changes are excluded from all Git diff queries via one shared command
boundary. Collection excludes registered gitlinks and `.gitmodules` paths from
both discovery and directory copies, without requiring Git for non-Git projects.
Regressions cover committed additions/updates/deletions and changed/dirty
submodules from root/subdirectories with both `diff.relative` settings, as well as
repository-wide scope and cached site reuse. Rendering gitlink content and
per-query root-relative path workarounds are no longer needed. The explicit
worktree comparison mode and empty deleted sides remain required.

Set `REPORT_TEST_PLUGINS` to a generated client's absolute `plugins/` directory to
exercise bundled entrypoints. Loopback tests launch from a subdirectory and
verify default cache selection, `--project-dir`, cancellation, failed ngrok and a
simulated running tunnel. Windows uses a new process group and Ctrl+Break to
exercise graceful cancellation; forceful OS termination cannot run cleanup.
No live ngrok authentication is exercised by these tests.

Reports can be run directly with `python /path/to/plugin/scripts/<command>.py`.
Use repeated `--test-dir DIR` for platform-independent custom report roots;
`--test-dirs`, `TEST_RESULT_DIRS`, and `REPORT_DIRS` retain legacy colon separation.
Use a fresh output directory after upgrading old collected report caches.

## Consuming-project integration rules

The collaboration skill owns the shared independence principle; the documentation skill applies it to README, DEVELOPMENT.md and AGENTS.md. Each project-facing skill also carries a short domain-specific boundary so standalone installation does not depend on the general plugin. Keep routed agent prompts consistent with their owning skills.

Review changes against both sides of the boundary: using a device lock, emulator, report viewer or remote test environment must not insert AI-plugin paths/flags into a project; required Gradle plugins, Appium extensions and reporting libraries must remain declared. Explicitly requested AI-plugin integrations and the plugin's own repository are in scope for their implementation documentation. Validate portable skills independently, then regenerate both clients and validate copied instructions, manifests, routing and package resources. Do not add wording-matching tests for this documentation-only rule.

## Plugin rule audit

The audit compares rules, agent prompts, examples and README claims with their
owning runtime, profile defaults, portable manifests and client generation. A
configurable default or bounded read-only probe is not automatically an obsolete
technical limit. Preserve actual ownership, protocol and resource constraints.

| Plugin | Confirmed findings and resulting behavior |
| --- | --- |
| qemu-guests | The default is now 128 ports (20000–20127) on both platforms. Explicit larger pools remain supported without a count ceiling. Batch registration, actual bind/nofile failures, Docker cache seeding, disjoint outbound ports and lifecycle leases remain necessary. Authorization wording honors existing requests. |
| android-emulator-profile | Removed global AVD lock deletion, unqualified ADB shutdown and forced DISPLAY fallback. Per-AVD launch guards protect configuration; native locks require inspection. Existing/custom userdata resize needs explicit wipe permission; fresh AVDs configure size before first data creation. Profiles no longer use eval. AVD name lookup is exact; arm64 is supported as an architecture alias. SDK downloads use temporary storage, keep replaced tools and respect existing ownership. |
| android-device-lock | Atomic mkdir alone did not serialize expired-lease takeover or token-read/delete races. A device-side guard now covers all mutations and atomic metadata publication. A bundled JSON template renders explicitly JSON-encoded placeholders through the shared metadata helper. Strict JSON/type checks reject corrupt, incomplete, duplicate-key or non-finite records; quoting/control characters round-trip through Python 3. Unknown metadata and interrupted guards are retained; tokens stay out of timeout output. Failed remote deletion retains the recovery token and makes release/run fail without replacing an existing command failure. Fixed leases require bounded commands/manual renewal and the same guarded helper version across participants. |
| diff-sharing | The documented local fallback now runs when ngrok is absent or authentication fails. Python 3 aliases are verified, loopback binding is explicit, local-only previews are available, and cancellation cleans only owned children. Fixed the agent's incorrect site-generator filename. |
| test-report-sharing | Same server/auth/lifecycle corrections; documented directory alias now works. XML copying creates its destination, retains duplicate basenames from different paths and counts successful copies. Parent HTML roots are processed before children to avoid duplicate copies; output cannot recursively collect itself. Nested XML is linked from the site. |
| client-ui-best-practices | Kotlin/Swift examples preserve cancellation and reject superseded completions. Serial executors/actors do not serialize whole requests across suspension; React has the same asynchronous ordering requirement. Clarified portable/client routing language. |
| recyclerview-best-practice | Aligned state/effect ownership with the shared Host rule. A sentinel changes diff positions but does not guarantee visible insertion or anchoring when offscreen. Paging headers require ConcatAdapter or insertHeaderItem, not mapping alone. |
| kotlin-coding-practices | Explicitly rethrow CancellationException when converting coroutine failures. Structured concurrency, immutable snapshots, sealed state variants and narrow platform interop boundaries remain appropriate. |
| general-coding-practices | Reviewed both skills and the documentation agent. Canonical README/DEVELOPMENT/AGENTS ownership, root-cause diagnosis, focused verification and privacy rules remain current; no cosmetic rule removal was needed. |

Reviewed integration guidance distinguishes the ADB server from an emulator's
specific endpoint and checks gvproxy's existing host route before Windows port
proxies. It no longer prescribes a blanket restart of shared IP Helper services.
Current [Android command-line guidance](https://developer.android.com/studio/run/emulator-commandline)
is referenced without automatically replacing the explicit profile workflow.
SDK/image/package pins are setup choices, not capacity ceilings or claims that
every installed version accepts the same flags. Status limits remain bounded
read-only IO/display budgets. Claude routing remains generated from extensions;
Codex skills remain unchanged copies of their portable sources.

Focused audit regressions:

```bash
bash plugins/qemu-guests/tests/test-port-ranges.sh
bash plugins/android-device-lock/tests/test-device-lock.sh
bash plugins/android-emulator-profile/tests/test-start-avd-docker.sh
bash plugins/android-emulator-profile/tests/test-install-sdk.sh
bash plugins/test-report-sharing/tests/test-collect-test-results.sh
python3 tests/test-report-launchers.py
python3 tests/test-validation-workflow.py
```

The device and SDK/emulator fixtures use fake commands and private temporary
files; they do not establish real-device behavior, native SDK installation,
macOS/arm64 execution, or successful public ngrok authentication. Launcher tests
use real loopback HTTP and simulated ngrok failures/running tunnels, checking
responses and owned-process cleanup. Prompt-only changes are checked for source
and package integrity and reviewed against API semantics; no model behavior or
compiled Kotlin/Swift application result is claimed. Shared real devices, VM
disks/images and existing report services are outside these fixtures.

Run `bash scripts/build-claude-plugin-package.sh --all` and `bash scripts/build-codex-plugin-package.sh --all` to generate sibling directories. Inspect existing sibling checkouts first: generated `plugins/`, marketplace directories, and README are replaced; unrelated files are preserved. Do not commit or push generated repositories locally.

Run `python scripts/validate-plugin-packages.py --client claude ../me.claude` and `python scripts/validate-plugin-packages.py --client codex ../me.codex`, plus `bash tests/test-build-plugin-cli.sh` and `python tests/test-plugin-packages.py`. The Python test covers generated content, routing, regeneration, cleanup, and path protection; the shell test covers both client command entries, help, arguments, and dispatch. Validation dependencies are in `scripts/requirements-validation.txt`.

The sync workflow needs `UPSTREAM_GITHUB_TOKEN` with repository write and pull-request permissions for both existing destination repositories. It opens a separate generated PR for each client; destination PRs must merge before users receive updates. Start a new Codex thread after synchronized plugin updates are published and installed.

Sync PR titles include the source commit subject. `scripts/render-sync-pr.py`
renders the shared `scripts/templates/sync-pr.md.template` with affected plugin
versions (including removals), generated diff statistics, completed client checks,
and source/run links. The workflow refreshes both title and body for existing PRs.
The renderer runs after the generated sync commit and compares it with its parent.

## Code design skill ownership

The former Kotlin plugin is consolidated into `general-coding-practices`, whose
`code-design-rules` entrypoint owns language-independent control-flow, state, and concurrency invariants.
One-shot callback adapters must settle once and clean up; repeated listeners use
owned streams with explicit buffering and termination.
Keep native APIs, state examples, cancellation differences, documentation terms,
and platform test guidance in its `references/` files. Link each supported platform
from the entrypoint and keep the plugin README/platform metadata aligned. The
Kotlin plugin and skill identifiers are retired; generated marketplace cleanup
removes the old package and includes the new skill in both clients. Validate source
frontmatter separately and use the distribution checks above to verify all reference
resources and unchanged Codex skill copies. Prompt checks do not prove application
or model behavior.

## Continuous integration

Two validation workflows run on every pull request, pushes to `main`, and
manual dispatch. `validate-client-packages.yml` (Validate client packages)
validates all portable sources and both Codex and Claude distributions.
`test-plugins.yml` (Test plugins) runs plugin runtime suites and checks that
every suite is connected to CI. They use separate concurrency groups.
Together they cover:

- All eight portable plugins and both generated client distributions, including
  prompt-only plugins, skill frontmatter, agent routing, resource integrity,
  regeneration, CLI behavior, and generated Codex skill checks.
- `diff-sharing` and `test-report-sharing` shell suites in separate matrix jobs.
- Android status UI, backend, browser checks, and emulator startup regressions.
- QEMU status UI, backend, browser checks, and VM shell regression suites.
- Windows Git Bash with a separate MSYS2 installation and xorriso, checking
  fallback PATH ordering and proxy environment delivery to child Bash.
- Docker proxy Go tests with the race detector.
- The unprivileged QEMU container runtime smoke test.

Python, npm, uv, Go, Playwright Chromium, and Docker build layers use Actions
caches. Browser system dependencies are installed on every fresh runner even
when Chromium is cached. Package checks run once, independently of runtime
jobs. New executable plugins must add their runtime suites to `test-plugins.yml`;
all plugin manifests and portable prompts are automatically included in package
validation. Prompt checks verify packaging and structure, not model behavior.

Run `python tests/test-validation-workflow.py` to check runtime suite coverage
when changing CI.

Run shell suites with `bash plugins/<plugin>/tests/test-*.sh` one file at a time,
UI suites with `npm ci`, `npm run build`, and `npm test` in their UI directory,
and browser/backend suites with `uv run --script <test.py>`. Run proxy tests
with `go test -race ./...` in `plugins/qemu-guests/scripts/docker-proxy`.
The container job requires Docker and a Linux runtime; see its workflow steps
for the build and execution commands.

## Device lease controller

`android-device-lock/scripts/adb-device-lock.py` owns host lease operations.
The shell entry selects Python 3.10+; `lock-metadata.py` remains an importable
strict metadata validator with a compatible command entry. Device mutations
remain serialized through the remote mkdir guard. The owner token is persisted
before metadata publication and retained on remote deletion failure.
Run `bash plugins/android-device-lock/tests/test-device-lock.sh` for fake-device
races and failures, and `python plugins/android-device-lock/tests/test-controller.py`
for native controller and cancellation checks. No real-device result is implied.

Command ownership uses a Windows Job Object with a launch gate: user code starts
only after the wrapper is assigned to the job. Cleanup terminates the job and
waits for its active process count to reach zero. Unix cleanup signals the process
group even after the root exits. A cleanup error retains the device lease.
Native controller tests include signal-resistant descendants, normal root exit,
cleanup failure, and Python/Bash shebang argument forwarding. They run in both
Linux and Windows CI. Windows job semantics follow the
[Job Objects API](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects).

`command_tree.py` owns platform-specific command lifetime; `command-worker.py`
is the gated Windows launch entry. The lease controller only starts, waits and
stops that owner, then releases on confirmed cleanup. Cancellation handlers are
suppressed during cleanup and restored afterwards.

## VM lifecycle and state controllers

`vm-state.py` owns state guards, operation tokens, singleton reservations and
atomic identity/PID publication. `lib/vm-state.sh` is a compatibility facade for
provisioning and clients. Generic shell callbacks use token-checked Python guard
acquisition/release; shell callback failure and signals still release that guard.
`vm_phase.py` defines immutable lifecycle snapshots, process-evidence variants and
legal transitions. `vm_lifecycle.py` owns start/stop, readiness and failure cleanup;
`vm-lifecycle-step.sh` retains platform/guest planning and guest probes. Native
QEMU creation and handle publication belong to Python; only legacy provisioning
paths still require Bash PID mapping. Python directly owns and joins native gvproxy controller subprocesses;
the helper still verifies executable/creation time. Provisioning remains staged
shell orchestration, marking creation uncertain before each QEMU launch and using
the same Python registration/termination paths. Native Windows launcher PIDs carry an explicit marker so they
are not interpreted as MSYS PIDs. Unknown identity inspection returns a distinct
failure status from a confirmed absent/unrelated QEMU process.

Run `python plugins/qemu-guests/tests/test-vm-state.py`, the existing
`test-vm-utils.sh` shell suite, `python plugins/qemu-guests/tests/test-vm-transitions.py`,
and `test-vm-lifecycle.py` with real QEMU and
`GVPROXY_BINARY` set to an existing verified helper. The lifecycle fixture uses
private state, mocked guest IO and an untouched synthetic disk; Windows launches
native Python in a new process group and tests Ctrl+Break cleanup. It does not
provision a real guest or inspect/stop another VM. Existing gvproxy controller
and lifecycle tests remain applicable.

VM client fixtures keep QEMU probes mocked while setting `QEMU_STATE_PYTHON`
to a real interpreter before installing fake commands on PATH. This exercises
operation lease acquisition/release rather than mocking away the state controller.

`test-vm-state.py` also injects failures at identity and both PID publication
boundaries, fails cleanup, and exercises later stop recovery with synthetic
process identities. It checks unknown/incomplete publication, cross-VM takeover
refusal and PID reuse without signalling real processes. Profile regressions use
the real Bash description adapter with private state, covering profile precedence,
environment isolation, defaults, SSH readiness and graceful/forced stop behavior.
The state owner resolves durable process evidence and compatibility PID/identity
files before mutation. `run/active-vm.lock/lifecycle.json` is one atomic snapshot
containing a reservation generation, phase and tagged process evidence. Native
identity is published there before legacy `.qemu.json`/`.pid` pointers; an incomplete
compatibility publication cannot erase ownership. Existing reservations without a
snapshot retain conservative legacy identity/PID recovery. A generation mismatch
rejects obsolete publication and cleanup. Operation lease tokens serialize whole
commands; the durable reservation outlives the command when a VM or unknown launch
remains. An existing helper/controller blocks acquisition even without a VM lock.

| Phase | QEMU evidence / ownership | Cancellation or failure |
| --- | --- | --- |
| No reservation | No resources owned by this command | Release only its operation lease; never clean an existing VM after an idempotent health-check failure. |
| `reserved` | This generation owns the global reservation; no new QEMU | Clean only this operation's resources, then release the reservation. |
| `network-starting`, `network-ready` | No QEMU; native network controller must exit before cleanup can proceed | Join/cancel the controller, stop its owned helper, then release. If controller exit cannot be confirmed, retain the operation lease to prevent late publication. Logs/preflight IO happen before process creation. |
| `spawning` | Creation outcome may be unknown | Defer handled signals through handle assignment or definitive `Popen` failure rollback. A known creation failure returns to `network-ready`; a forced/interrupted unknown launch remains reserved. |
| `launched` | Native or legacy shell PID persisted before identity inspection | Verify the native executable and creation time. Failure/unknown identity retains helper and reservation; a verified process may be stopped. |
| `registered` | Immutable native identity is durable; compatibility pointers may be incomplete | Stop the verified QEMU, join this command's adapter, then stop networking and clear ownership. |
| `ready` | Readiness committed; background VM owns its reservation | This is the start completion boundary. A later cancellation does not undo the committed VM. |
| `stopping` | Preserve the same process evidence during shutdown | Graceful/forced stop cancellation retains ownership for a later stop; release only after QEMU exit and helper/controller cleanup are confirmed. |
| `recovery-required` | Preserve the last process evidence after failed start cleanup | A later owned stop can retry. Unknown creation/inspection or failed cleanup requires inspection, never age-based lock removal. |

Successful cleanup removes the reservation (the terminal stopped state). Installer
cleanup with `keep-lock` instead resets to `reserved` for the verification boot.
Nested state guard mutations (including teardown) defer rather than drop signals;
acquisition and creation finish bounded ownership publication before delivering
cancellation. Readiness and helper network IO never run inside the state guard.
Additional signals are ignored only during final cleanup and handlers are restored.

`resource_ownership.py` supplies the same nested cancellation boundary to VM state,
QEMU launch and gvproxy controllers. Establish the cleanup scope before acquisition;
finish handle assignment or definitive creation-failure rollback before delivering
a handled signal. A failed metadata write to a guard created by the current call
removes that new guard, so a later operation can retry. A pre-existing guard is
never reclaimed this way. The helper controller owns its exclusive reservation
through creation, identity publication and readiness; cancellation before identity
publication still kills and joins its process handle before removing the pending
record. Failed termination or a bounded join timeout retains the pending/published
evidence for inspection. Network readiness stays cancellable outside the boundary.

`test-vm-transitions.py` checks the complete legal/illegal phase matrix, evidence
validation, generation replacement, cancellation at lease/guard/acquire/spawn/READY
boundaries, log-open and definite creation failures, every atomic publication
boundary, failed cleanup/retry, stop cancellation and borrowed VM/helper protection.
It uses synthetic processes and private state. The real lifecycle fixture also
fails log opening after starting an isolated real helper and cancels its native
controller at a private fixture barrier before QEMU creation. It checks full cleanup
then exercises normal start/stop/cancellation without opening its synthetic disk.
`test-gvproxy-control.py` deterministically delivers each supported handled signal
after creating a real private child and before returning its handle. It asserts
the child has exited before ownership disappears, and covers failed creation,
repeated cancellation during cleanup, failed kill/join and existing guard protection.
The state suite injects failures before and after each initial guard metadata write,
checks rollback and retry, and preserves pre-existing unknown guards. The original
guard leak and creation-window orphan both fail these tests on the earlier code.

Shell claims use caller-generated tokens and preinstalled token-checked cleanup.
The internal `vm-state.py begin` and `guard-acquire` CLI actions require `--token`;
`new-token` performs no resource acquisition. `publish_claim` defers cancellation
through creation and local ownership assignment and rolls back its own claim if
metadata publication or flushed output fails. Before creation the Shell already
knows the token, so unsuccessful delivery or a later nonzero creator exit cannot
lose the cleanup capability. Guard rollback is idempotent and checks owner/token;
it never removes another caller's or an unknown guard.

`claim_vm_state` temporarily records handled Shell signals while waiting for its
exec'd native creator, joins that process even if `wait` is interrupted, restores
the caller's traps, then reports cancellation. Rollback cannot run ahead of a
creator that may still publish. `begin_vm_operation keep-traps` preserves existing
build cleanup, while failed acquisition also rolls back before returning to an
error-handling caller. This protocol covers handled cancellation and known errors;
forced termination and unconfirmed cleanup still require inspection.
Nested acquisition by an already-owning Shell is rejected before changing its
token or traps; other failed requests restore the caller's previous context.

Run `python plugins/qemu-guests/tests/test-vm-shell-handoff.py` for actual
CLI-to-Bash tests with private state. The fixture interpreter injects cancellation
at metadata/output boundaries, output failure and a nonzero exit after publication.
Separate barriers hold creation before/after publication; a Shell trap marker proves
signal delivery before allowing the creator to finish. Tests cover both resources,
normal/custom traps, rollback/retry and preservation of existing unknown owners.
## Emulator profile controller

`profile_controller.py` owns literal profile decoding, tool lookup, argument
mapping and atomic INI replacement. Profile configuration stays in a dictionary
(or a shell associative map), separate from inherited process environment.
Only explicit Android path/display contracts are forwarded to tools. `start-avd.py` owns the per-AVD guard and
emulator process. Shell installation orchestration uses only the internal `profile`, `tool` and
`args` bridge modes, without eval. AVD path resolution and INI reads/updates are
called directly by the native startup controller. Native Windows waits are bounded so Ctrl+Break reaches cleanup;
only the owned process tree is terminated. Run the existing fake SDK/emulator
shell suites and `python plugins/android-emulator-profile/tests/test-profile-controller.py`.
The native test covers spaces/Unicode paths, CRLF, expansion rejection,
arguments, duplicate keys, native locks, competition, failure and cancellation,
plus ignored inherited configuration/wipe permission and batch trailing-backslash
rejection. Run the native suite on both Windows and Unix.
The Git Bash smoke suite delegates Windows signal coverage to that native test.

## QEMU profile configuration boundary

The shared `lib/config.sh` parser stages literal values before publishing a fresh
file configuration. Its fixed supported-key namespace clears inherited or stale
VM settings and removes export attributes. Shell consumers read those ordinary
configuration values; lifecycle adapters receive the profile path explicitly.
Host tool/path/interpreter controls stay outside the profile namespace. Alpine
ISO defaults resolve when used, after profile loading. Guest/test environments
continue to receive only explicit command contracts.

`test-vm-state.py` checks ignored inherited lifecycle settings, missing required
values, child-environment isolation, successive loads and protected host settings.
The synthetic lifecycle fixture sets readiness timeouts in its profile.


## Scoped command ownership and report publication

The canonical scoped command runtime lives in `scripts/process-runtime/`.
Run `python scripts/sync-process-runtime.py` after changes; `--check` verifies
bundled copies in emulator and both report plugins. CLI main-thread creation
handoffs defer cancellation until handles are owned. Windows uses a gated worker
assigned to a kill-on-close Job Object before user code runs; stop waits for zero
active job processes. Unix cleanup targets the process group after root exit too;
commands must not daemonize or detach workers. Persistent QEMU services use their
existing phase/generation/identity owner, not the scoped kill-on-exit abstraction.

`AvdSession` owns configuration serialization and its command scope. Cleanup
failure retains its guard. QEMU normal startup directly creates native argv from
the shell plan, persists typed native launch evidence and registers the
verified process before readiness. Native launch variants and structured pending-PID
records distinguish native PIDs from legacy shell PIDs without a sidecar flag. Old
shell PIDs keep their translation path;
unknown launch or identity failures still block takeover and preserve recovery.

Both report plugins build a complete site in a private sibling staging directory,
rename it into `generations/<id>`, then atomically replace `current.json`. The
pointer is the publication boundary. Failure before pointer replacement leaves
the previous site intact; interrupted publication can leave an unreferenced
complete generation or a sibling `.building-*` directory. Confirm its generator
has stopped before manual removal. Site assembly reuses complete immutable sites;
legacy flat caches are materialized and published once. Linked asset files and
directories are materialized into the snapshot; directory cycles
abort the build without replacing the previous version. No published generation
is edited or automatically deleted. The HTTP root redirects to the
current generation's URL, so each page's relative assets remain pinned even while
another build publishes. Flat caches without a pointer remain readable during
migration. Automated consumers resolve `current.json` before reading report files;
summary report paths are relative to their generation. Clear a dedicated cache
only after servers/readers have stopped; there is no automatic retention policy.

Run `python tests/test-report-snapshots.py`, `python tests/test-report-python.py`,
`python tests/test-report-launchers.py`, emulator `test-command-tree.py` and
`test-profile-controller.py`, and QEMU `test-vm-state.py`/`test-vm-transitions.py`.
Tests cover failed publication, overlapping builds, idempotent collections,
old-asset URLs, invalid refs, failed renderers, cancellation handoffs and native
PID recovery. The native suites also run on Windows CI. QEMU's lifecycle fixture
uses real native QEMU/gvproxy with private state, mocked guest IO and no guest disk.

General code guidance now prioritizes structural ownership, lifecycle, state and
interface fixes over compensating patches, while retaining evidence and explicit
recovery for crashes, uncertain effects and partial publication.

Android tool environment construction normalizes the three Android directory
variables on Windows after applying profile overrides. The native regression
passes Git Bash paths containing spaces and Unicode directly to a Python child,
covering inherited values, profile overrides, native paths and empty values.

### Real Alpine guest acceptance

`plugins/qemu-guests/tests/validate-guest-testcontainers.py` is an opt-in
real-guest check, separate from the deterministic fake-process CI suites. Run it
through the plugin's Testcontainers wrapper against a freshly provisioned isolated
VM after building its CLI proxy. It checks cgroup v2 CPU quota and memory limits,
actual OOM enforcement without swap, mapped HTTP readiness, active Ryuk and
workload removal. Provisioning regression checks reject `cgroupfs-mount` while
retaining OpenRC's `cgroups` service; real installation validates that this service
is supplied by Alpine rather than asserting a foreign package name.

System provisioning uses Alpine's `lbu` archive when `setup-disk` installs the
persistent root filesystem. Register the supervised Docker wrapper with `lbu include`
before `setup-alpine`; an executable merely present under the live ISO's
`/usr/local` is otherwise absent after reboot. Real fresh-disk verification must
check both the persisted OpenRC configuration and the referenced executable.

Windows CI also exercises ANSI-default Python text IO. Git Bash path conversion
and generated UTF-8 report artifacts must specify their encoding explicitly; do
not rely on the host locale or enable UTF-8 mode merely to hide missing boundaries.
The native path regression simulates CP1252 while converting a real Unicode path.

The test-environment protocol CI matrix runs provisioning, immutable snapshot,
transport cleanup, cancellation and worker ownership regressions on Linux and
Windows. Its fixtures use simulated processes and do not start existing VMs;
Node tests also verify the guest Appium launcher and macOS auto-login helper.
