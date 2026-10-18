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
Native tests cover bounded scans, repeated directory arguments, overlapping roots,
recursive output rejection, URL/HTML escaping, binary Git statistics, committed
comparisons and invalid input. Difftastic regressions also cover subdirectory
invocation with either `diff.relative` setting and committed/worktree deletions
whose paths were re-created locally. Gitlink tests cover additions, updates,
deletions with objects absent from the parent repository, and checked-out
submodules with changed commits or dirty files, alongside ordinary file diffs. Set `REPORT_TEST_PLUGINS` to a generated
client's absolute `plugins/` directory to exercise its bundled entrypoints. Loopback tests exercise cancellation, failed ngrok
and a simulated running tunnel. Windows uses a new process group and Ctrl+Break
to exercise graceful cancellation; forceful OS termination cannot run cleanup.
No live ngrok authentication is exercised by these tests.

Reports can be run directly with `python /path/to/plugin/scripts/<command>.py`.
Use repeated `--test-dir DIR` for platform-independent custom report roots;
`--test-dirs`, `TEST_RESULT_DIRS`, and `REPORT_DIRS` retain legacy colon separation.
Default output cache keys use the native Python working-directory path, so
regenerate an old shell-created cache or provide the same explicit output path.

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
