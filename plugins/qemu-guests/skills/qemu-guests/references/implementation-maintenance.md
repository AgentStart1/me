# Plugin implementation and validation

Read this only when changing this plugin's runtime, lifecycle, transports, provisioning or status UI. Routine application tests use the selected operational reference; they do not require rebuilding QEMU or running this plugin's regression suites. Full test commands and evidence belong in [DEVELOPMENT.md](../../../DEVELOPMENT.md).

## Backend ownership and publication

- Whole-operation leases also protect setup and VM clients from concurrent lifecycle changes. Do not bypass a busy lease. After forced termination, confirm all plugin lifecycle/client processes have exited before removing interrupted `run/vm-operation.lock`, `vm-state.guard` or a helper `.control.lock`; preserve process records until both owned processes are confirmed stopped.
- Cleanup verifies QEMU/gvproxy native executable and creation time before signalling. Healthy repeated starts check forwarding rules, SSH, Docker and the publish pool. For Windows provisioning and legacy shell records, use the launching Bash runtime for path/PID conversion; normal native starts keep their original PIDs; bypass HTTP proxies explicitly for `127.0.0.1` instead of passing a wildcard to curl.
- Missing PID pointers do not prove QEMU exit. Recover partial publication through the pending launch PID and native identity; retain networking and reservations when publication or inspection remains unknown. See the configuration and recovery reference for profile lifecycle options.
- Follow the lifecycle snapshot's phase and reservation generation. Before creation, clean only this launch's resources; after creation, verify QEMU exit before stopping its helper. Never adopt existing helper ownership or bypass a recovery-required reservation. A completed ready VM survives cancellation of the already-completed start; a cancelled stop can be resumed with another owned stop.
- Resource creation and cleanup share one cancellation handoff rule: defer handled signals through handle assignment or definitive failure rollback. Failed initial metadata publication removes only the guard created by that call. Helper cancellation joins the owned process before removing pending state; failed kill/join retains evidence. Never apply this rollback to a pre-existing guard or helper reservation.
- For CLI-to-Shell claims, generate the token and install matching cleanup before acquisition. Join the native creator before cancellation rollback, retain custom cleanup traps, and release only the same owner/token. Use the shared shell facade; the internal begin/guard-acquire CLI requires a caller-known token. Failed delivery does not authorize removal of an existing unknown lease or guard.
- Render provisioning configuration from `templates/*.tpl` with the shared `render_template` helper; keep scripts limited to runtime values and orchestration.

## Managed Windows runtime

Keep each build bound to its single immutable BuildSnapshot through cache selection, compilation, packaged inputs, manifest and verification. Changes to source templates/patches belong to later invocations; never re-fingerprint or relabel an in-flight build. Inspect remaining build processes before clearing an interrupted build lock. Validate guest boot-time changes, four guest-visible processors and unchanged QEMU native identity with `tests/validate-whpx-reboots.py`, then authenticated Appium readiness and concurrent work-guest acceptance. Each reboot must also recover the interactive Appium service within the same cycle deadline; SSH returning first is not acceptance. Cold supervisor relaunches do not count as warm reboot success. Legacy explicit system-runtime profiles may retain a bounded `install_reboots` budget; never mistake those for the default managed path. Do not generalize the result to Windows 10, other CPU models or UEFI installations without testing them.

## Initialization and test orchestration

Use TestEnvironmentOwner for the lease and all guest-test resources. Persist retention at the resource failure boundary before other cleanup runs; later exceptions must never unlock an uncertain environment. Use the immutable initialization snapshot for requirements, script bytes, fingerprint, preflight and seed generation. Never re-read hook paths during seed assembly, mutate detached views to change a captured install, or serialize script bytes into the VM metadata record. Verify these contracts with the isolated owner/snapshot suites; leave native QEMU smoke disabled unless explicitly authorized.

GuestTransport owns its SSH children: attempt every child stop before reporting aggregate cleanup failures. Preserve cancellation after draining cleanup and retain the environment lease on failure. Verify with tests/test-transport-cleanup.py using mocks; never start existing VMs for this regression.

Configured test execution must share one CancellationRequest between CLI, TestEnvironmentOwner and transports. Follow the three invariants in DEVELOPMENT.md: only the main thread commits cancellation/phase/lease state; workers publish reliable events and sticky cleanup failures; release and terminal publication require closed admission, confirmed resource-worker completion and final event collection. Signals only enqueue requests. Workers read committed snapshots at checkpoints and never construct or replace shared cancellation. Keep main-thread cleanup shields context-local. Report stop failures before HTTP conversion and worker completion, retaining them even if a later retry succeeds. Reject worker attempts to mutate owner/CLI state. Preserve existing assertions and the documented cancellation priority, including the identity of an accepted interruption. Never reintroduce frame inspection, asynchronous signal exceptions, handoff retries or nested handler replacement. Preserve the documented lifecycle contracts when changing test orchestration; deliberate changes to the shared process runtime or VM-management commands need their own affected regression checks.

Publish one immutable CliResult/CleanupReport after worker reports and all cleanup have been accounted for. Emit fixed failure categories/counts and the accurate acquired-lease recovery hint, never raw cleanup exceptions, commands, paths or credentials. Unconfirmed workers or failed retention publication must preserve ownership evidence. Verify tests/test-worker-protocol.py plus the existing cancellation, CLI, owner, transport and relay suites with QEMU_TEST_ACCEL unset. Use mocks/local fixtures; do not start, stop or repair existing VMs for these regressions.

## Offline checks and live acceptance

Run regression suites from the plugin directory in the `me` source checkout; these need the repository test helpers. For affected backend helpers, the following suites use fixtures rather than a live VM:

```bash
python ./tests/test-apk-mirror-selection.py
python ./tests/test-vm-utils.py
python ./tests/test-port-ranges.py
python ./tests/test-sync-workspace.py
python ./tests/test-build-docker-proxy.py
```

`build-docker-proxy.sh` is a separate live backend operation that can install Go and compile code. It is not part of the offline suite above. Native boot, reboot, UI and Testcontainers acceptance are separate scoped runs on fresh isolated resources; do not start or repair existing VMs merely to validate documentation or mocked regressions.

On Windows, the status collector translates Git Bash/MSYS PIDs before verifying the native QEMU process and accelerator. A missing process is stopped; failed inspection remains unknown. Rebuild the panel with Node on Windows or Linux after UI changes.
