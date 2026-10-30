# Host-driven test execution

Read the [unified entry point](../../../README.md#unified-test-environment-entry-point) and the sections below that match the project's runtime and transport needs. Reuse the project's existing commands and apply SKILL.md's build-placement and project-independence rules.

## Runtime requirements and initialization

Keep portable dependency requirements in the consuming project: Java/Appium versions, normal driver/plugin dependencies, system runtime libraries, prebuilt native classpath coordinates and desktop dimensions. Keep VM hardware, media, SSH, accelerator settings, prebuilt bundle locations and operator launcher commands outside that project. Use `scripts/prepare-appium-runtime.py` to package prepared local extensions, prebuilt assets and the Windows host-compiled display helper. `--requirements` with `--platform` also executes project-declared host preparation hooks. Use `scripts/guest-vm.py install <private-profile> --requirements <project-requirements>` for automated desktop setup. Fresh initialized Linux guests supply their prepared JDK/native metadata without a private Linux transport override.

Project `hooks.host_prepare` may build/download/stage on the host. Project `hooks.guest_setup` may run self-contained initialization scripts after offline runtime extraction, with explicit arguments and bounded timeouts. Review scripts before running them. Guest hooks configure runtime state and install prebuilt dependencies under the common build-placement rule. Never encode consuming-project scripts or commands in this plugin. Fail and preserve private logs when hooks fail or time out; do not skip failed initialization. Prepare all shared host artifacts before running E2E and keep them immutable during active UI tests.

Keep large archives out of cloud-init YAML: extract the seed payload from read-only media instead. Poll cloud-init status without creating long-lived waiters. Verify SSH host-key pins using the supervised QEMU-owned listener and preserve the per-VM pin for later connections. The isolated Linux test display is distinct from the console framebuffer shown in the panel.

## Execute and collect results

Use `bash scripts/run-test-env.sh --config <project-environment.json> -- <host test command>` for configured host tests with Docker and/or guest Appium transport. Supply connections through operator-owned `TEST_ENV_DOCKER_PROFILE` / `TEST_ENV_GUEST_PROFILE`; project JSON declares portable workspace, property, file/directory, cleanup and launch roles, including optional prebuilt `artifacts`. The old `run-testcontainers.sh` forwards to this entry point for compatibility.

The proxy adapter supports quoted JVM argument files for Windows host/guest and Windows/Linux host to Linux guest. It stages classpath/JDK/agent artifacts after host compilation, mirrors private inputs and outputs, forwards declared loopback service ports, preserves guest state across application restarts, and collects outputs back to their original host paths. Never ship the host Windows JDK into Linux. Fail unsupported adapters instead of guessing. The transparent `java-argfile` relay does not support macOS; use a prepared operator-owned Appium launch adapter for that target.

Previously prepared/custom Linux environments can use an operator-owned `TEST_ENV_LINUX_RUNTIME` override containing a dedicated POSIX mirror root, an existing guest Java executable and prebuilt host native classpath additions, plus an optional Appium port. Prepare an isolated graphical Appium session, D-Bus/AT-SPI and an unlocked test keyring outside the project. Map declared roles and classpaths and send launch capabilities to the guest Java runtime. Run native diagnostics through Appium on the application machine; never make clients attach to guest PIDs locally.

## Failure and cleanup

Use shell-free SSH forwarding channels and confirm every forward acknowledgement; never keep remote shells waiting on stdin. Keep Windows SSH scripts on the bounded stdin transport rather than inlining growing artifact lists into encoded command-line arguments. Roll back a newly created Appium session if output handoff fails, retaining ownership when deletion is uncertain.

Lost, malformed or interrupted Appium creation responses require retaining the cleanup-uncertain lease and private inputs until the operator confirms remote cleanup. Never bulk-delete sessions or clear that lease automatically. Preserve private failure logs and report the original test result and any unconfirmed cleanup separately.

When changing the proxy, transports, initialization snapshots or cancellation code, read [maintenance and validation](implementation-maintenance.md) before implementation.
