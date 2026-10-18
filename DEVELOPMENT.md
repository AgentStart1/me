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

Run the existing shell suites in both plugins, `python tests/test-report-python.py`,
`python tests/test-report-launchers.py`, and `python tests/test-validation-workflow.py`.
Native tests cover bounded scans, custom project directories, overlapping roots,
recursive output rejection, URL/HTML escaping, binary Git statistics, committed
comparisons, and invalid input. Diff commands enter the Git root once during
argument parsing, aligning statistics, both renderers and cache identity. Test
report commands enter `--project-dir` (default: caller cwd). Explicit output paths
are made absolute before entering the project. Cache identity uses that project.

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

## Plugin rule audit

The audit compares rules, agent prompts, examples and README claims with their
owning runtime, profile defaults, portable manifests and client generation. A
configurable default or bounded read-only probe is not automatically an obsolete
technical limit. Preserve actual ownership, protocol and resource constraints.

| Plugin | Confirmed findings and resulting behavior |
| --- | --- |
| qemu-alpine-docker | The default is now 128 ports (20000–20127) on both platforms. Explicit larger pools remain supported without a count ceiling. Batch registration, actual bind/nofile failures, Docker cache seeding, disjoint outbound ports and lifecycle leases remain necessary. Authorization wording honors existing requests. |
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
bash plugins/qemu-alpine-docker/tests/test-port-ranges.sh
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
with `go test -race ./...` in `plugins/qemu-alpine-docker/scripts/docker-proxy`.
The container job requires Docker and a Linux runtime; see its workflow steps
for the build and execution commands.

## VM lifecycle and state controllers

`vm-state.py` owns state guards, operation tokens, singleton reservations and
atomic identity/PID publication. `lib/vm-state.sh` is a compatibility facade for
provisioning and clients. Generic shell callbacks use token-checked Python guard
acquisition/release; shell callback failure and signals still release that guard.
`vm_phase.py` defines immutable lifecycle snapshots, process-evidence variants and
legal transitions. `vm_lifecycle.py` owns start/stop, readiness and failure cleanup;
`vm-lifecycle-step.sh` retains platform/guest planning and launching Bash PID
mapping. Python directly owns and joins native gvproxy controller subprocesses;
the helper still verifies executable/creation time. Provisioning remains staged
shell orchestration, marking creation uncertain before each QEMU launch and using
the same Python registration/termination paths. Native Windows launcher PIDs carry an explicit marker so they
are not interpreted as MSYS PIDs. Unknown identity inspection returns a distinct
failure status from a confirmed absent/unrelated QEMU process.

Run `python plugins/qemu-alpine-docker/tests/test-vm-state.py`, the existing
`test-vm-utils.sh` shell suite, `python plugins/qemu-alpine-docker/tests/test-vm-transitions.py`,
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
environment fallback, defaults, SSH readiness and graceful/forced stop behavior.
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
| `launched` | Launching Bash PID persisted before identity inspection | Verify the native executable and creation time. Failure/unknown identity retains helper and reservation; a verified process may be stopped. |
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
