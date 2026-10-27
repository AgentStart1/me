# QEMU Guests

This plugin runs concurrent QEMU work VMs alongside one persistent Alpine Linux Docker backend, inside Linux containers and on Windows. Work guests have independent disks and unattended installation media. Work guests are independent test environments with Appium; host-side test runners connect over SSH. The Alpine backend remains available independently for host Docker/Testcontainers.

For Docker-only workflows on ordinary Linux hosts, use Docker directly. The work-guest supervisor also runs on Linux hosts with QEMU and Python installed.

## Project independence

Consuming projects use standard Docker/Appium endpoints and portable artifact/service configuration without depending on this AI plugin's installed launcher path or private VM profiles. Normal Appium drivers/extensions, Gradle plugins and other required project dependencies remain documented prerequisites; operator setup stays outside the project.

## Concurrent work VMs

The plugin was renamed from `qemu-alpine-docker` to `qemu-guests`. Install the new name after the client distributions publish. Existing Alpine disks and keys deliberately stay in `~/.qemu-alpine-docker`; `QEMU_ALPINE_BASE_DIR` remains the backend storage override. No disk is moved or recreated by the rename. The VM & Containers panel shows both the backend and registered work VMs, with live read-only screens for running graphical guests.

| Guest | Unattended provisioning | Requirements |
| --- | --- | --- |
| Ubuntu | Official cloud image with NoCloud seed, SSH and Appium bootstrap | Verified amd64 cloud-init qcow2 image |
| Windows | Bundled Autounattend.xml and PowerShell bootstrap | English amd64 BIOS-compatible ISO, matching image edition and available Windows OpenSSH optional features |
| macOS | Recovery terminal automation, `startosinstall`, first-boot product package and Appium LaunchAgent | Prepared English Intel macOS installer ISO, matching firmware/OpenCore hardware, Tesseract on the host and a bootstrap product package built on macOS |
| Other | Custom seed and QEMU installation arguments | OS-specific unattended installer and bootstrap |

The Windows template uses BIOS/MBR with IDE storage and an e1000 NIC. It targets compatible Windows 10/Server media; stock Windows 11 TPM/UEFI and arm64 installers are not bundled. Use a custom adapter for other firmware, drivers or installer requirements. The built-in macOS flow targets Intel Recovery installers with `startosinstall --volume --installpackage`; Apple Silicon IPSW restoration is a separate workflow.

The Windows sample defaults to four vCPUs and `qemu_runtime: "whpx-reset"`. On Windows 11 x64, `install` and `run` build or verify the plugin-managed QEMU 11.1.2 runtime before starting the guest. This runtime contains WHPX only and uses `Westmere,-vmx,-svm`; build or accelerator failures stop the operation without falling back to TCG. Installation uses guest warm reboots in the same QEMU process. `plan`, `status` and `stop` never trigger a build. Ubuntu's sample also selects WHPX explicitly; on Linux select `qemu_runtime: "system"` and KVM.

Install MSYS2 UCRT64 and Python 3.12+ for the managed build. The builder discovers MSYS2 at `~/msys2` or `C:/msys64`; set the host control `QEMU_MSYS2_ROOT` for another installation. The first build installs the required MSYS2 compiler packages, downloads and checks pinned source, applies the bundled reset and CET/XSAVE patches, and packages the executable, dependent DLLs and firmware under `~/.cache/me/qemu-whpx/<version-recipe>/runtime`. Each build freezes its template, ordered patches and source metadata before selecting the cache. Later source edits apply to a subsequent invocation; the active build keeps its captured inputs. It never overwrites system QEMU. Existing QEMU image tools (`qemu-img`) remain required for disk creation. Source, logs and failed build workspaces remain in the cache for inspection. After an interrupted build, inspect `build.lock` and remaining compiler processes before removing that lock.

To prepare the runtime ahead of guest installation:

```powershell
python scripts/whpx_runtime.py
```

The normal Windows profile needs no executable path or extra DLL PATH setup. Its complete runtime is selected automatically and every cached file is verified before launch. An explicit `qemu` path keeps existing profiles on the system/custom runtime; use `qemu_runtime: "system"` to opt out of management. Do not combine `whpx-reset` with a `qemu` override or an installer cold-boot budget.

Four-vCPU cold startup succeeded with QEMU 11.1.2 and `qemu_args: ["-accel", "whpx", "-cpu", "Westmere,-vmx,-svm"]`. The unmodified executable still failed guest-initiated warm reboot with `Unexpected VP exit code 4`. Switching to Q35, UEFI or masking x2APIC did not resolve the tested failure. Upgrading QEMU alone does not establish compatibility.

The bundled [WHPX partition-reset patch](patches/qemu-11.1.2-whpx-partition-reset.patch) adapts an [upstream proposal](https://patchew.org/QEMU/20260421205749.55060-1-mohamed@unpredictable.fr/) and is not part of the stock release. Four-vCPU Windows Server 2025 warm reboots passed on Windows 11; the current Appium mode also passed a host-run desktop end-to-end case. The reboot acceptance probe waits for authenticated Appium readiness after every restart within the existing cycle timeout; SSH readiness alone is insufficient. See [build and verification instructions](DEVELOPMENT.md#whpx-four-vcpu-windows-reboots). The reset API requires Windows 11 on x64; Windows 10 and patched UEFI installations are not validated.

The managed runtime also includes a [CET/XSAVE capability fix](patches/qemu-11.1.2-whpx-cet-xsave.patch). WHPX host defaults cannot enable CET features excluded by the selected guest CPU model or unsupported by its XSAVE/XSAVES state path. This prevents exposing shadow stacks to the pre-XSAVE Westmere model. A changed patch selects a new runtime cache; existing VM processes and disks are left untouched.


An experimental CPUID-cache runtime has completed a Sonoma 14.8.9 installation on Windows 11 WHPX with four vCPUs and 4 GiB RAM. Desktop login, SSH version/CPU checks and registered QMP capture passed after repairing first-boot service loading and SSH access-group membership. Docker verification was omitted. This used a private Recovery adapter; it is not end-to-end acceptance of the bundled full-installer ISO flow. See DEVELOPMENT.md for the scope and remaining limitations. The managed Windows runtime remains unchanged. Recovery keyboard input separates presses/releases and waits for a shell prompt before installation handoff.

Public reports match these symptoms: [QEMU #2042](https://gitlab.com/qemu-project/qemu/-/issues/2042) describes four-vCPU WHPX reboot failures, and [#2402](https://gitlab.com/qemu-project/qemu/-/issues/2402) describes Windows/UEFI reboot hangs. The [qemu-virgl-whpx project](https://github.com/Tsuki-Bakery/qemu-virgl-whpx#Windows-guests) provides Windows guest launch examples but also lists reboot failure as a limitation. Linux KVM configurations such as [dockur/windows](https://github.com/dockur/windows) are useful installation references, not evidence of a WHPX reboot fix.

For legacy system-runtime profiles only, `install_reboots: 4` explicitly allows up to four cold boots during Windows installation. QEMU exits instead of resetting internally; after a clean pre-acceptance exit, the supervisor starts it again with the same disk, seed and accelerator, selecting the disk before installer media. Crashes, stop requests, exhausted budgets and the original readiness deadline stop this flow. Acceptance checks guest bootstrap and Appium readiness. The managed runtime rejects this option because it supports warm reboot directly.

Each work VM has its own `state_dir`, qcow2 disk, supervisor lease and host SSH port. Multiple work VMs can run simultaneously. Assign different host SSH ports and keep them disjoint from Alpine's host forwards. Work guests do not require Alpine and receive no Docker proxy, backend credential or container-port tunnel.

### Unified test environment entry point

`bash scripts/run-test-env.sh --config /path/to/test-env.json -- <host command>` combines Docker/Testcontainers setup and transparent guest Appium transport. The former `run-testcontainers.sh` remains a thin compatibility entry point; `--profile <alpine.profile>` keeps the original Docker-only behavior, operation lease, CLI proxy, Ryuk, metrics and command exit code.

Test-environment JSON is separate from VM provisioning JSON. `version: 1`, `workspace`, optional `docker.profile`, optional `appium` and optional string `environment` values select services without project-specific code in this plugin. Paths resolve relative to the workspace; the workspace resolves from the config's directory. `${VARIABLE}` expansion is supported for private profile paths; unset variables fail before testing. Operator environment variables `TEST_ENV_DOCKER_PROFILE` and `TEST_ENV_GUEST_PROFILE` supply private connections when the project omits `docker.profile` or `appium.guest`. With no Docker selection, Docker is left unchanged. Project documentation must describe endpoint requirements and ordinary test commands, not AI plugin installation paths or provider-specific setup. See `profiles/test-env-windows.json` for the explicit role schema.

Windows transport sends PowerShell scripts through SSH standard input with UTF-8/base64 framing, keeping remote command arguments bounded for complete suites. PowerShell and native command failures retain their exit status. Forwarding channels use SSH without a remote shell, avoiding idle guest processes across repeated tests. If output collection fails before a new session reaches the client, the proxy deletes that owned session; uncertain cleanup retains the guest lease. The transparent Appium adapter supports Windows host/guest and Windows/Linux host to Linux guest JVM launches through a quoted Java argument file. It transfers updated host-built classpath and Java agent artifacts at session creation, after compilation finishes. Windows also stages the host Java runtime. Linux uses a prepared target JDK and explicit prebuilt native classpath additions from an operator-owned runtime manifest; it never copies a Windows JDK into Linux. Named JVM properties in the config declare private inputs, output files, required directories, additional built `artifacts` (for example diagnostic agent JARs), and HTTP/WebSocket service URLs. The proxy mirrors those files, creates authenticated reverse forwards for loopback services and returns the original WebDriver responses. PID/output files are collected before session creation returns; logs are also collected on page-source requests and session shutdown. Private guest state survives application restarts and is removed only when the host command finishes, within explicitly declared per-case cleanup roots. It never runs a guest compiler or substitutes a local desktop when transport fails.

The runner supplies `APPIUM_DESKTOP_SERVER_URL` to host tests. Native diagnostics belong on the Appium server and return results through Appium; never attach to a guest PID on the host. Client-specific Java property names belong only in that project's configuration. Existing Appium window compatibility extensions remain project prerequisites. Other host/guest combinations and launch formats fail explicitly until a corresponding adapter is implemented. No VM is started or provisioned merely by running this wrapper.

Linux operators set `TEST_ENV_LINUX_RUNTIME` to a private JSON manifest with absolute POSIX `root` (dedicated artifact mirror directory), `java` (existing guest Java executable), `classpath` (host paths to prebuilt Linux native/runtime JARs), and optional `appium_port` (default 4723). For example:

```json
{
  "root": "/home/tester/.local/share/test-environments/runtime",
  "java": "/usr/lib/jvm/java-21-openjdk-amd64/bin/java",
  "classpath": ["/operator/prebuilt/linux-native-runtime.jar"],
  "appium_port": 4727
}
```

Initialize the isolated graphical Appium session from project requirements as described below. For previously prepared/custom runtimes, the operator must provide the required Linux driver, D-Bus/AT-SPI and unlocked test keyring before invoking the unified entry point. The relay maps host paths and JVM classpath separators into the dedicated POSIX mirror, forwards the declared host services and retrieves output files to their original host paths. Windows and Linux test-environment JSON use the same `java-argfile` schema; the guest profile selects the transport. Projects declare normal platform, artifact and service requirements only; do not add these operator manifest paths or environment-provider instructions to consuming projects.

### Automatic desktop runtime initialization

Projects may keep portable `version: 1` desktop requirements beside their environment JSON, selected with its `requirements` field. The requirements file contains `desktop` width/height and a `platforms` map (`Windows`, `Linux`): required Java major version, Appium server version and driver/plugin name-to-version maps, optional Linux runtime `packages`, required environment-variable names and prebuilt Maven `classpath` coordinates. It contains no VM profile paths, SSH keys, accelerator selection or AI-plugin entry points. The project owns normal Appium extension source/dependencies and runtime requirements; operators own prebuilt bundles and platform connections.

Use `prepare-appium-runtime.py --base <offline-runtime.zip> --output <new-runtime.zip> --extension <prepared-extension-directory>` to overlay target-compatible local extensions without guest npm/install hooks. `--windows-desktop` compiles the display helper on the Windows host. `--assets <private-assets.json>` bundles prebuilt directories/files and service environment values (`${RUNTIME}` expands to the installed runtime). Its `files` entries contain `source` and relative `destination`; optional `classpath` maps Maven coordinates to bundled `assets/...` JARs. Asset paths, artifact caches and environment values stay outside consuming projects. Supply target-compatible prepared dependencies; never copy a host-native dependency tree into a different guest OS.

Pass `--requirements <project-requirements.json> --platform windows|ubuntu` during runtime preparation to run declared host preparation hooks and check the completed bundle. Then install with `guest-vm.py install <private-guest.json> --requirements <project-requirements.json>`. The VM profile describes hardware, media, WHPX/KVM and connections; desktop dependencies come from the project requirements. Runtime metadata must match the guest system and x64 architecture (Windows win32, Ubuntu linux, Intel macOS darwin). Missing or mismatched platform/architecture metadata fails before disk creation, including installs without project requirements. Legacy bundles without arch metadata must be rebuilt on the host for new preparation/install operations; this does not revalidate, rewrite or stop already installed VMs during normal run/test operations. Host preparation with requirements rejects a foreign base runtime before running host hooks. Missing extensions/versions, native artifacts or required runtime environment values also fail before disk creation. Existing disks are never reset; use a distinct state directory for blank-disk acceptance.

Ubuntu seeds carry only small cloud-init text and extract the offline payload from read-only seed media. Runtime packages are installed as distribution binaries. Initialization creates an isolated Xvfb/Openbox desktop, D-Bus/AT-SPI session, temporary unlocked native keyring and Appium service; LightDM auto-login also enables manual console use. The status panel projects the console framebuffer; the isolated test display is separate. Windows uses a persistent auto-login account, applies 100% DPI, warms reboots under the selected accelerator, sets the configured mode through a host-built assembly and launches Appium in the interactive session. No display helper is compiled in a guest.

Fresh managed guests pin their SSH key to the state directory's `known_hosts` after verifying that the supervised QEMU owns the SSH forwarding listener. Later transport and Appium connections use that pin. Readiness polls cloud-init status without `--wait`; abandoned SSH probes must not leave cloud-init waiters consuming guest memory. Java/runtime checks and real project E2E remain distinct from Appium server readiness.

Linux guests initialized this way provide an existing `/usr/bin/java` and bundled native classpath metadata automatically. `TEST_ENV_LINUX_RUNTIME` remains an optional private override for previously prepared/custom environments. The unified host entry point checks the initialization fingerprint against project requirements before testing.

### Project setup hooks

Each platform's requirements may include `hooks.host_prepare` and `hooks.guest_setup` for dependencies that cannot be expressed declaratively. Host entries contain `command` (literal argv array), `cwd` (relative to the requirements file) and `timeout_seconds`. Guest entries contain a self-contained `script` path relative to the requirements file, `interpreter` (`bash`, `powershell` or preinstalled `python3`), literal `arguments` and `timeout_seconds` (1–3600). Host hooks run during runtime preparation, before tests. Guest scripts are copied into private seed media and run after runtime extraction, before Appium is started. Linux setup runs as the provisioning administrator; Windows runs as the installation test administrator. Guest hooks receive `TEST_DESKTOP_USER` and `TEST_RUNTIME_ASSETS` as opaque runtime context; use these rather than hard-coding a provider username or installation path. Scripts must stay in the foreground and wait for their own tools; detached installers are unsupported.

For example, a Linux platform entry can add project-owned hooks (paths resolve from the requirements file):

```json
"hooks": {
  "host_prepare": [
    {"command": ["python3", "scripts/prepare-runtime.py"], "cwd": ".", "timeout_seconds": 600}
  ],
  "guest_setup": [
    {"script": "scripts/configure-runtime.sh", "interpreter": "bash", "arguments": ["--mode", "test"], "timeout_seconds": 120}
  ]
}
```

A guest hook authorizes runtime configuration and installation of prebuilt dependencies; it does not authorize guest compilation. Keep compilers/build tasks in host hooks. Review project scripts before executing them, retain raw hook logs privately, and stop initialization on nonzero exit or timeout. Project requirements and guest scripts are read into an immutable initialization snapshot once. Preflight, seed generation and the recorded fingerprint use that snapshot, even if the original files are edited or removed during installation. Changes apply to the next capture. Guest script fingerprints include ordered file identifiers and individual content digests. Moving content between scripts invalidates initialization too. Environments recorded before fingerprint v2 require a new isolated initialization for guest-hook configurations. Existing v2 fingerprints remain compatible when inputs are unchanged; configurations without guest hooks retain their existing fingerprint. Existing VM state is never rewritten automatically. Generic engine code must not contain consuming-project package names, paths or test commands.

### Cancellation and cleanup

Configured local, Docker-only and guest Appium runs share the same cleanup and cancellation behavior. Signals record the first cancellation request; execution responds at explicit checkpoints rather than being interrupted in arbitrary instructions. Command and SSH waits check requests in short intervals; startup HTTP readiness remains bounded by its 10-second timeout. Once cleanup begins, further signals cannot interrupt it or replace the execution result. An accepted cancellation keeps its signal exit code even when cleanup fails; clean execution keeps the host command's exit code. Ordinary cleanup failure returns 1. Commands and cleanup are never restarted to publish a result. Worker cleanup failures remain recorded even when an HTTP request converts the exception into an error response or a later retry succeeds. The main thread confirms resource workers have finished and collects their reports before deciding whether the test lease can be released. The CLI reports fixed cleanup categories/counts without exception text, arguments, paths or credentials. Uncertain guest cleanup retains the desktop test lease and prints a manual-recovery hint; local/Docker-only runs acquire no guest desktop lease. Fully confirmed cleanup releases the lease and emits no cleanup warning.

### Uncertain Appium creation

If a session creation response is lost, malformed or lacks a valid session ID, the relay blocks further creation and retains the guest test lease as `cleanup-uncertain`. It preserves private test inputs because the application may still be running. The test environment owner persists retention at each failed resource-cleanup boundary before attempting the remaining cleanup. Later transport or temporary-directory errors cannot release that lease or hide retention. Ordinary test failures still release the lease after all owned resources close successfully. SSH transport attempts to stop every owned tunnel even if another stop fails, then reports the failures together and retains the lease for inspection. Cancellation remains the final outcome even if cleanup fails: the environment owner drains all registered resources, rethrows the original cancellation and attaches the collected cleanup errors. A cancellation with fully confirmed cleanup releases the lease normally. During teardown, handled cancellation signals are deferred until every cleanup result and the lease decision are committed. Repeated signals cannot interrupt failure recording or lock retention; confirmed clean teardown still releases the lease before propagating cancellation. The closed relay rejects delayed requests before they can launch new work. The same applies to interruption while a creation request is in flight. Do not retry by deleting the lease automatically: inspect that guest's Appium sessions/processes and private test diagnostics, confirm the affected application/session has stopped, then explicitly recover only that run's lease. Never bulk-delete unrelated Appium sessions. Confirmed protocol rejection and failures before the remote request allow ordinary cleanup. The default regression suites do not start QEMU; native multi-VM smoke requires an explicit QEMU_TEST_ACCEL opt-in and runs separately.

### Build and test placement

Work VMs are runtime/test environments. Unless the user explicitly requests guest compilation, compile applications, test code, native dependencies and installation hooks on the host or an existing designated build environment, then transfer built artifacts and prebuilt dependencies. Requests to install a guest, configure Appium or run tests do not authorize compiling in the work VM. Never silently fall back to guest compilation or increase its CPU/RAM to accommodate a build; resolve host-side build prerequisites or report the limitation. Work VMs run Appium, applications and tests; ordinary runtime JIT execution is not a build step.

### Provision and run

1. Install media authoring support: `python -m pip install -r scripts/requirements-guests.txt`.
2. Generate a guest access key: `ssh-keygen -t ed25519 -f ~/.ssh/qemu-work`.
3. Prepare an offline Appium runtime on the same OS and CPU architecture as the target guest. Use a standalone official Node.js distribution and a supported npm first; distro/Homebrew executables linked to private external libraries are not portable guest runtimes. The builder pins Appium 3.2.2 and never starts an application on the preparation desktop. For Windows desktop tests:

   ```bash
   python scripts/build-appium-runtime.py /private/appium-windows.zip --driver appium-desktop-driver@2.8.0
   ```

   Repeat `--driver <pinned-npm-package>` for project-required drivers and `--plugin <pinned-npm-package>` for Appium plugins (activated from runtime metadata); omit it for an Appium server without drivers. Driver prerequisites, SDKs, JDKs and application artifacts belong to the consuming project. Linux local drivers and macOS Xcode/accessibility permissions need their platform-specific preparation; installing the server alone does not prove UI automation works.
4. Copy a sample JSON profile outside the checkout. Supply vendor media and verified SHA-256, guest key, and `appium.runtime_archive` / `appium.sha256` from the builder. `appium.host_port` selects a unique host loopback port for its SSH tunnel. Paths resolve relative to the profile; `~` expands to the host home. Set the exact Windows image edition. Seeds generate private account credentials.
5. Inspect the plan and install in a dedicated terminal:

   ```bash
   python scripts/guest-vm.py plan /path/to/ubuntu.json
   python scripts/guest-vm.py install /path/to/ubuntu.json
   ```

   Installation is unattended and supervised in the foreground. `Guest ready` means acceptance succeeded: authenticated SSH plus a ready guest Appium server, and cloud-init completion on Ubuntu. The supervisor stays running throughout the guest's lifetime. Start another guest in another terminal. Logs live in `state_dir`.
6. From another terminal, inspect or stop an individual VM; restart it later with `run`:

   ```bash
   python scripts/guest-vm.py status /path/to/ubuntu.json
   python scripts/guest-vm.py stop /path/to/ubuntu.json
   python scripts/guest-vm.py run /path/to/ubuntu.json
   ```

   Stop requests ACPI shutdown; the supervising terminal reports completion. `stop --force` terminates only that session's verified native QEMU. Ctrl+C cancels the supervisor and forcibly stops its owned QEMU. If a supervisor was killed, inspect the recorded native process before removing retained locks or process records.

Connect host tests to the guest server in a separate terminal:

```bash
python scripts/connect-appium.py /path/to/windows.json
# Point your project's Appium client at http://127.0.0.1:<appium.host_port>
```

Appium listens only on guest loopback port 4723. OpenSSH authenticates and pins the guest host key; on first connection verify its fingerprint through the guest console or another trusted channel. The tunnel binds only host loopback, refuses occupied ports and ends with its owning process. The status panel displays the configured endpoint, which requires this tunnel. Each guest uses a separate tunnel/host port.

Windows Appium runs as the dedicated test user in the interactive guest session, never SSH Session 0. That account automatically logs in after reboot. Do not use personal credentials in this disposable test environment. Manual testing can use an independently configured guest console or remote desktop connection; the status screen remains read-only. Tests must stage their own apps and files on the guest and arrange access to their host/backend services. Changing only an Appium URL does not translate local paths or loopback URLs. The plugin contains no project path, application or test selection.

macOS desktop UI automation requires a project-required Mac2 driver and a compatible full Xcode installation; Command Line Tools alone is insufficient. Verify Apple's signature on supplied Xcode archives, select the installed developer directory and complete license/first-launch initialization. WebDriverAgentMac needs a build prepared on a designated macOS build environment, or an explicit exception authorizing that build in the work VM. Grant the built runner and Xcode Helper Accessibility permission in the dedicated test account. Rebuilds may invalidate that grant. Validate a real session, native source, screenshot and click; server readiness alone is not UI acceptance. See the [Mac2 setup documentation](https://appium.github.io/appium-mac2-driver/v4/getting-started/).

Old work profiles with `backend` / `proxy_binary` are intentionally rejected: remove those keys and add `appium`. Existing disks are never replaced. On Windows, copy the new rendered payload into `C:/ProgramData/qemu-guests` and run its bootstrap to replace the plugin-owned Docker task/environment/credentials. Refresh the private guest auto-logon password from its existing account when migrating an old disk. Ubuntu/macOS operators must remove their old plugin-owned Docker tunnel/service, environment entries and backend key before applying the new Appium bootstrap. Provisioning a new private state directory is the fully unattended path.

Seeds contain generated guest account credentials and SSH authorization. Keep state directories private, outside repositories and shared folders, including on Windows. Never publish seeds, answer files or payload archives. Installation refuses to replace existing disks/seeds. Resume an interrupted install with `run`; media stays attached until acceptance succeeds. Accepted guests boot without installation media.

### Graphical systems and live screens

Set `graphical` to a JSON boolean. Ubuntu defaults to `false`; Windows and macOS default to `true`. A graphical guest requires a unique host `qmp_port`, separate from SSH, backend and other guests' ports. QMP binds only to `127.0.0.1`. The panel does not expose the monitor or accept keyboard/mouse input.

```json
"graphical": true,
"qmp_port": 2241
```

Ubuntu installs XFCE, Xorg and LightDM when graphical; a headless Ubuntu guest omits them. Accounts use SSH keys; set a desktop login password through your authenticated guest administration session if needed. Windows images are selected using the install WIM/ESD metadata: `graphical` chooses the matching Windows Server desktop or Core variant. Use an edition name from your media; naming conventions differ between releases. Windows client editions do not have a Server Core variant. macOS retains its native graphical OS components even in headless operation; `graphical: false` disables panel screen sharing, while Recovery automation still uses its private QMP connection.

Size the guest desktop for the test suite's largest window at the selected DPI. A basic macOS framebuffer can expose only the boot-selected mode: configure the private OpenCore `UEFI -> Output -> Resolution` (for example `1920x1080` when supported), restart the guest, and verify its actual display mode before testing. Keep the original firmware/configuration available. An SSH disconnect during macOS shutdown can precede kernel halt; wait for guest shutdown before forcing the owned QEMU process to exit.

Starting/installing a VM registers its public status metadata in `~/.qemu-guests/registry`. Stopped VMs remain listed. The panel distinguishes booting, ready, stopping, stopped, unknown and recovery-required states; an orphaned process is not reported ready. Choose **View screen** to switch between graphical guests. Frames refresh about every two seconds while visible. A failed capture retains the previous frame with an explicit error; screenshots are not included in ordinary status snapshots. Runtime capture files are temporary and deleted after every request. The screen tool accepts only a registered guest ID and verifies process identity and ownership of its loopback QMP listener.

### Unattended Intel macOS installation

Apple provides installer downloads through [its documented channels](https://support.apple.com/102662). The open-source [OpenCore macrecovery tool](https://github.com/acidanthera/OpenCorePkg/tree/master/Utilities/macrecovery) also runs on Windows and downloads Recovery images from Apple servers with chunklist/signature verification. Recovery download does not require an existing Mac. A Recovery image alone does not contain the full installer application and private bootstrap product package required by this adapter, and is not interchangeable with the prepared installer ISO below. The sample selects WHPX explicitly with no TCG fallback; complete the CPU arguments and firmware/OpenCore configuration for the selected macOS release before attempting installation. The tested macOS WHPX runtime is the experimental CPUID-cache variant described above; stock QEMU compatibility is not implied. Linux hosts must select KVM explicitly.

1. Prepare a full English Intel-compatible installer application on a macOS preparation machine. Run `scripts/create-macos-media.sh /path/to/Install-macOS.app /absolute/installer.iso`; it uses Apple tools and a newly created dedicated disk image. Record and verify the resulting media checksum.
2. Complete `profiles/macos-adapter.json` with compatible private firmware/OpenCore configuration, the actual installer app path under `/Volumes/`, an explicit target serial such as `serial:work-target` matching the disk device's `serial=work-target` (recommended over unstable BSD disk numbers), Appium runtime, access key, media checksum, and the host Tesseract executable. Supply a USB controller/keyboard in `hardware_args`; the GPT installer image is attached as a read-only USB disk so OpenCore can recognize its HFS+ partition. Configure the OpenCore timeout and hide its own EFI entry with `.contentVisibility` to avoid a self-boot loop. Firmware settings belong to your boot configuration, not the panel.
3. Export the private first-boot payload with `python scripts/prepare-macos-payload.py /path/to/macos.json /private/payload.zip`. On the preparation Mac, build `scripts/build-macos-bootstrap.sh /private/payload.zip /private/bootstrap.pkg`. Copy that product package to the profile's `macos.bootstrap_package` path. Keep both files private; they contain a generated account password.
4. Run `guest-vm.py install` as for other guests. The controller waits for Recovery using bounded OCR, opens its Terminal with a keyboard shortcut, and hands off to the attached seed's fixed install script. That script refuses a partitioned target, formats only the explicitly configured empty guest disk (matched by serial when selected), and runs `startosinstall` with the bootstrap product package. It never clicks through Setup Assistant or silently retries a destructive handoff after a crash.

The bootstrap product package explicitly loads its first-boot service when installed on the running target; it does not load that service into a preparation or Recovery host. First boot adds the configured user to an existing restricted SSH access group and marks the per-user setup screens complete before the final reboot. For Sequoia it also clears the separate Terms cookie left by an installation already invoked with `--agreetolicense`.

For an explicit OS upgrade, prepare a new private bootstrap package using the
existing test account's credential and SSH authorization, and supply it to
`startosinstall --installpackage` along with `--agreetolicense --nointeraction`.
Installing that package on the running target rearms first boot. Retain the
original disk and validate the upgrade on an independent copy before adoption.

5. The installed package supplies a first-boot LaunchDaemon that creates the guest account, enables SSH, installs Appium as a per-user LaunchAgent, completes initial setup and reboots. First boot clears the installer’s one-time login flag and configures persistent loginwindow automatic-login credentials for the dedicated test account, preconfigures the standard QEMU USB keyboard as ANSI, keeps the desktop awake and removes the temporary password file. Other keyboard devices/layouts require their own matching preferences. Appium startup avoids the stock Git shim’s developer-tools installation dialog when no toolchain is selected; it preserves an explicitly configured toolchain and does not install build tools. FileVault must be off; provisioning fails rather than disabling encryption. Final acceptance requires authenticated SSH, the expected console user, the user-session Appium LaunchAgent and a ready loopback Appium server. A completed OCR/key handoff alone does not establish installation success.

Preparation requires Apple tools (`createinstallmedia`, `pkgbuild`, `productbuild`, `hdiutil`). The Windows/Linux runtime can consume the resulting ISO/package but cannot build them with substitute tools. Installer versions, firmware and boot layouts must match; retain incomplete disks and inspect `macos-install.json` after an interrupted handoff. Do not erase a partially installed guest automatically. The bundled rendering/control tests do not replace installation testing with your selected macOS release.

### Windows macOS GPU runtime

For the qualified Intel macOS 15.8.1 (24H32) experiment on Windows 11 x64,
use `profiles/macos-reims-whpx.json` as the starting point for a private profile.
Its `qemu_runtime: "reims-whpx"` builds and verifies a dedicated WHPX-only QEMU,
the Windows Reims Vulkan library and its option ROM. The plugin contains the
three external dependency patches and pins their public source commits; it
does not require a sibling development checkout. Existing Windows guest
profiles keep their separate `whpx-reset` runtime.
A native Windows Vulkan driver with compatible `VK_EXT_external_memory_host`
support is required. This is not the WSL/Dozen path or a general GPU pass-through
solution; native GPU checks remain necessary on each host.

Install a GNU Rust toolchain (`rustup toolchain install stable-x86_64-pc-windows-gnu`)
and MSYS2 UCRT64 development tools: GCC toolchain, Git, Clang/LLVM/LLD, CMake,
Make, Ninja, Python, pkgconf, GLib, pixman and libslirp. Use `QEMU_MSYS2_ROOT`
when MSYS2 is not in its usual location. Prepare the runtime explicitly with:

```powershell
python scripts/reims_runtime.py
```

The clean-source qualification used GNU Rust 1.99.1 and UCRT64 Clang/LLVM 23.1.3;
new compiler or graphics-driver versions require native qualification again.

The first build downloads pinned sources and Cargo/QEMU build dependencies.
It retains logs and failed workspaces in `~/.cache/me/reims-whpx`; a verified
runtime is reused by subsequent launches. Never remove a busy build lock.
QEMU's build system rejects source paths containing spaces. Set
`QEMU_REIMS_CACHE` to a private path without spaces, such as `C:/qemu-cache`,
when the default cache path contains them; this also selects that cache for
managed profile launches. `--cache-dir` overrides it for a standalone build.
The executable, dependent DLLs, firmware, license texts and patch recipe are
bundled together and checksummed. The qualified Windows presentation path is
headless QMP capture; the launcher selects `REIMS_VGPU_WINDOW=0` for this
runtime. Native SDL presentation is unqualified. This stack accelerates Metal
rendering; it does not add VideoToolbox hardware video decoding.
For cold-boot qualification, request a normal shutdown inside macOS and confirm
the recorded native QEMU process has exited before relaunching. Do not race an
ACPI power-button request with a second shutdown over SSH. Sleep/resume remains
unqualified; preserve a stalled instance for inspection.

This configuration also needs the supplied timing driver. Prepare a new copy
of an operator-owned OpenCore image before selecting it in the private hardware
configuration:

```powershell
uv run scripts/prepare-macos-gpu-boot.py --opencore C:/private/OpenCore.raw --output C:/private/OpenCore-gpu.raw --guest-build 24H32
```

The tool verifies and installs the bundled PvgTimingFix and pinned Lilu 1.7.2,
using captured bytes for checksum verification, writing and the final receipt.
Both the output image and its `.json` receipt must be new paths; neither may
replace the source. Failed attempts retain their new partial outputs for inspection.
The preparer
retains other kexts, disables the interactive boot picker and leaves the source
image and system volume untouched. The source OpenCore configuration must
already contain exactly one enabled `Lilu.kext` entry. It assumes a FAT
partition at byte 1048576;
use `--fat-offset` for a different known layout. An existing output is never
overwritten. Unknown guest builds fail before image creation; system updates
need a new review. Compatible Apple installer media, private OpenCore/OVMF
hardware configuration, bootstrap credentials and prepared desktop assets
remain operator prerequisites. The hardware configuration must provide the
Q35, Apple SMC, USB and SATA devices, OVMF and the newly prepared OpenCore image;
omit another display device because the example selects `apple-gfx-pci`.
No Apple OS image or private firmware/credential payload is distributed.

After installation, complete the prepared-desktop recovery sequence below and
verify actual GPU output before running the project's unchanged tests. Keep
runtime caches, boot images and private profiles outside consuming projects.

### Prepared macOS desktop recovery

After an unattended installation or an explicitly selected upgrade, use
`scripts/macos-desktop.py reconcile /private/guest.json --plan /private/desktop.json`.
Start the private manifest from `profiles/macos-desktop.json`: pin the tested OS
build, application bundle identifiers and CDHashes, and retain the private
bootstrap payload ZIP as the credential source. Unknown builds/signatures fail.
Use Python 3.10 or newer with Pillow installed and the host Tesseract executable
selected in the guest profile.

Supply Apple-signed Xcode and an already built WebDriverAgentMac bundle from a
designated preparation environment. Run WDA as a separate user LaunchAgent using
`xcodebuild test-without-building`; `macos-wda.plist.tpl` supplies the template.
The controller requires that service and uses `webDriverAgentMacUrl`. It never
falls back to guest compilation or borrows an Appium-managed WDA process, which
can be stopped when another driver session claims the server.

The offline Appium runtime must also contain the compatible Mac2 driver and its
dependencies for the guest CPU. A server-only archive can report ready without
any drivers. Native qualification imports the prepared Mac2 entry before
creating a session, so missing or incompatible dependencies fail early.

Optional manifest `files` contain `source`, a safe staging `name`, and `sha256`.
An optional `setup_script` installs those prepared artifacts and configures the
runtime. It runs as root with the test account as its first argument and may
read one credential line from stdin to restore that account's automatic login.
It must be idempotent and must not silently compile dependencies. Files are
staged in the account's `.qemu-guests-desktop-inputs` directory. Keep scripts,
archives, credentials and lifecycle/upgrade orchestration outside consuming
projects.

Preparation disables the idle screen saver for the dedicated test account;
password and system security policies remain unchanged. Native qualification
also checks the actual console lock state, because SSH/Appium can stay ready
behind a lock screen. `reconcile` can authenticate the dedicated account once
using the configured private credential, only after verifying its on-console
identity, the system loginwindow secure-input process and the visible password
field. The OS clears its own lock state after a successful login; no lock cookie
is deleted. `verify` never enters a login password and fails if still locked.
Automatic login recognition is qualified only for the English Sequoia
1920x1080 console; other locked layouts fail before entering a credential.

Use the root home for privileged toolchain initialization and restore the test
account's ownership on installed files in its home. Install user LaunchAgents
for the following automatic login rather than loading them from a root SSH
session. The prepared-desktop sequence is `prepare`, cold boot, `reconcile`,
then another cold boot and `verify`.

Recovery first restarts the reviewed WDA runner and tests actual desktop access.
Working grants remain enabled. Missing access triggers repair of only reviewed
applications through System Settings' native Accessibility rows and controls.
It checks typed bundle paths and enabled toggles, then restarts WDA to confirm
the repaired access. Only a recognized system authentication dialog may
receive the private account credential. It does not edit TCC databases or
disable system security policies. The UI adapter currently requires English
macOS and an ASCII test-account keyboard layout.
Permission authorization also requires one recognized password field and the
OS secure-input owner to match a reviewed system authorization process in the test account.
The prompt and process identity are checked again before typing. Missing or
ambiguous fields never fall back to the current keyboard focus. OCR authorization
recognition is qualified for the 1920x1080 Sequoia console.

`prepare` only stages the supplied runtime and session configuration, publishing
a `prepared` milestone. Use it before a planned cold boot; `reconcile` then reuses
that immutable prepared manifest instead of transferring the same archives again.
Setup-script bytes and the captured credential participate in the preparation
fingerprint, so changing either invalidates the prepared milestone.
When preparation must run again, matching archive checksums in the private guest
staging directory avoid redundant transfers. Replaced files must pass the guest
checksum check before setup proceeds.

`verify` installs nothing and changes no permission grants. Native qualification
checks the console account, Appium GUI service, text input/readback in a new
Finder window, two exact window sizes and a PNG screenshot. Only the new window
and owned sessions are closed. Optional named `checks` run explicit guest
argument arrays for additional qualification, such as a supplied GPU probe.
Finder acceptance alone does not certify GPU rendering or a business suite.
Stable system window numbers track the new window; existing Finder windows and
their geometry must remain unchanged.
The bundled transparent `java-argfile` launch relay currently supports Windows
and Ubuntu. macOS business tests require a separately prepared Appium launch
adapter; the GPU runtime and prepared-desktop controller do not add that relay.

Only successful qualification and confirmed cleanup publish
`state_dir/macos-desktop/state.json` as `ready`. Lost session identities or
unconfirmed deletion retain the guest test lease for inspection. Verify after
a cold boot, then run the consuming project's unchanged business suite.
Terminal receipts are published after resource/worker cleanup, while the guest
reservation is still held. A retained reservation always requires inspection,
even when a previously written receipt says `ready`.
Prepared media, firmware and compatible manifests remain prerequisites; this
command does not select or download arbitrary future macOS releases. Configure
the supplied firmware to boot the installed volume automatically; a desktop
permission controller cannot recover a VM waiting in an interactive boot picker.

### Custom unattended adapters

`os: custom` accepts a supplied unattended installer for other systems. macOS now has the built-in flow above.

- `seed_dir` contains flat automation files. The tool adds `payload.zip` with the Appium runtime and systemd/launchd or Windows bootstrap. Custom automation must install the payload, configure guest access and run the bootstrap. Other OS families provide their own bootstrap.
- `hardware_args` optionally replaces default disk/NIC arguments; placeholders are `{disk}`, `{state}` and `{ssh_port}`. Provide loopback SSH forwarding and preserve the user-network gateway or adapt the bootstrap. Defaults are x86-64 IDE/e1000.
- `qemu_args` applies on every boot, including acceleration and firmware. Managed Windows and the bundled Ubuntu sample select WHPX explicitly; use the system runtime with explicit KVM on Linux. Custom system-runtime profiles must name their accelerator rather than assume QEMU's default is hardware accelerated. Automatic acceleration probing remains a backend feature. Keep monitor/stdin and lifecycle under supervisor ownership.
- `install_args` applies before first acceptance and supports `{state}` and `{seed}`. It must boot automation that consumes the seed unattended. Generic media attachments use IDE CD-ROM; adapters must supply compatible controllers.
- `acceptance` is an optional host argument array, without implicit shell expansion, supporting `{state}` and `{ssh_port}`; it is required for custom guests. Return zero only after installation, access and the required Appium/test services work. Probes are repeatable, read-only and bounded to 15 seconds. Never use a successful no-op as installation acceptance.
- `timeout` bounds readiness in seconds (default 3600). Failures retain the installation disk/seed. OS/media changes require a new state directory. `media_sha256` is checked before disk creation.

See the vendor formats: [Ubuntu NoCloud](https://canonical-cloud-init.readthedocs-hosted.com/en/latest/reference/datasources/nocloud.html), [Windows unattended installation](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/automate-windows-setup). Apple's [Virtualization framework installer](https://developer.apple.com/documentation/virtualization/installing-macos-on-a-virtual-machine) is a separate platform flow, not a QEMU installer bundled here.

## Alpine Docker backend architecture

- Alpine is installed unattended to a persistent qcow2 system disk.
- Automatic acceleration uses `kvm + host` on Linux with accessible KVM, `whpx + host` on compatible Windows hosts, and `tcg,thread=multi + max` otherwise. Hardware acceleration exposes the host CPU features available through the hypervisor instead of the restricted `qemu64` baseline. Restart an existing backend through its normal owned lifecycle to apply this CPU change; disk recreation is unnecessary. KVM requires a compatible x86-64 host CPU; TCG emulates the instruction set on other hosts.
- Provisioning configuration is rendered from files under `templates/`; scripts supply explicit placeholder values instead of embedding generated files in heredocs.
- Shared shell behavior is loaded through `scripts/vm-utils.sh`, which initializes common paths and sources focused modules under `scripts/lib/` for runtime, configuration, templating, QEMU, guest access, Alpine images, and VM state.
- During first provisioning, Alpine selects the fastest mirror from its official list, upgrades the result to HTTPS, validates it, and falls back to the official HTTPS CDN when needed.
- Alpine DHCP and Docker containers use gvproxy DNS at `192.168.127.1`. Both UDP and TCP DNS are supported; no guest DNS proxy is installed.
- Docker and SSH start automatically in the guest.
- Docker exposes its unauthenticated API only through gvproxy's host loopback forward at `127.0.0.1:2375`.
- Docker automatically allocates published ports from `20000–20127` on both platforms; gvproxy forwards every TCP port in the selected range to the same guest port before QEMU starts.
- A backend lock permits one Alpine backend at a time and reserves its forwarded range. Work VMs have independent locks and can run concurrently. Backend lock-state changes use an atomic guard so launchers cannot overwrite each other.
- A separate operation lease spans setup, provisioning, start/stop and client commands (tests, Docker, SSH/SFTP, workspace sync and proxy builds). Competing operations fail before changing VM state. Normal exits and handled signals release the lease; after a forced kill, inspect all plugin processes before manually removing an interrupted `run/vm-operation.lock` or `vm-state.guard`.
- QEMU and gvproxy ownership records verify the native executable and creation time before termination. An already-running VM is accepted only after its forwarding rules and guest readiness match the profile. Windows provisioning and legacy shell PID translation use the launching Bash runtime's tools; normal starts retain native PIDs directly.
- Docker images remain on the qcow2 disk and are reused by later test runs. Do not recreate the VM or run `docker image prune -a` if cache reuse matters.
- Testcontainers Ryuk stays enabled and uses the guest Docker socket.

Host bind mounts are not directly available to the remote guest daemon. Use Docker build contexts or named volumes when tests need host files.

### Docker commands from Windows or the outer Linux container over SSH

For Gradle or other test commands that invoke the Docker CLI, compile the native proxy in the environment where the test process runs: Windows or the outer Linux container.

```bash
./scripts/build-docker-proxy.sh
./scripts/run-test-env.sh -- ./gradlew test
```

Start the VM before compiling. The script sends the proxy source over existing SSH,
installs Go in Alpine if needed, tests it there, and builds with `CGO_ENABLED=0` for
Windows amd64 or Linux amd64/arm64, according to the environment running the script.
It downloads the executable over SSH; no Go installation is needed on Windows or in the outer container.
Go and its caches stay in the persistent guest; temporary build files are cleaned up.
Use `--profile <path>` for a non-default VM profile.
The wrapper puts the proxy on PATH, so `docker build` filters the local context using Docker's
upstream ignore matcher and sends a tar archive over SSH to guest `docker buildx build --load`.
Dockerfile-specific ignore files override the context's `.dockerignore`. Project Gradle tasks
remain responsible for preparing distributions, selecting targets and naming images.
Other commands run in the guest without copying host files; host bind mounts and `docker cp`
are not translated. Named contexts, build secrets and SSH mounts are rejected until explicit
transport support exists. No unfiltered workspace transfer is performed.

The compiled helper is shared by all projects at `~/.local/share/me/docker-proxy/docker.exe`
on Windows, or `~/.local/share/me/docker-proxy/docker` inside the outer Linux container.
On Windows, `~` resolves to the Windows user profile; in a Linux container, it is the
container user's home directory. Persist that directory or rebuild the helper when replacing the outer container.
Use the same `QEMU_DOCKER_PROXY_DIR` override for compilation and test execution if necessary.

To copy a host workspace into the guest before running project-specific commands:

```bash
./scripts/sync-workspace.sh --remote-dir /root/my-project /path/to/project
```

The script sends a tar stream over SSH into a staging directory and replaces the destination only after the transfer succeeds, retaining the prior copy as `<destination>.previous`. It excludes `.git`, `target`, `node_modules`, `dist`, and `.env` by default; pass `--exclude <pattern>` for additional project-specific exclusions. It intentionally does not build or test the project.

## Prerequisites

Run the scripts from Bash on Linux or Git Bash/MSYS2 on Windows with:

- QEMU (`qemu-system-x86_64` and `qemu-img`)
- Optional `/dev/kvm` device access on Linux or Windows Hypervisor Platform on Windows; TCG needs neither
- `xorriso`
- OpenSSH client and key generator
- `curl`, `tar`, and `sha256sum`
- A running Alpine VM with repository access for the first Go installation and dependency download

On Windows, known MSYS2 tool directories and Windows OpenSSH are appended to
`PATH` as fallbacks. Existing commands retain priority, including the Bash runtime
used to launch the scripts. This also makes MSYS2's `xorriso` available without
replacing Git Bash's tools.

## First-time provisioning

```bash
./scripts/setup.sh
./scripts/create-vm.sh ./profiles/dev.profile
```

`setup.sh` downloads and verifies the official Alpine virt ISO. `create-vm.sh` builds the unattended ISO, selects the configured accelerator, directly boots the kernel for deterministic automation, selects and persists a usable package mirror, configures Docker to use gvproxy DNS, boots the disk once, verifies DNS, Docker, and the selected repositories, then writes the persistent ready marker. Mirror selection happens only while provisioning a new disk. If a disk exists without the ready marker, the script stops and preserves it for inspection instead of silently rebuilding it.

When the install log proves that disk installation completed and only post-boot verification failed, resume verification without reinstalling:

Set `VERIFY_EXISTING=true` in a recovery profile, then run:

```bash
./scripts/create-vm.sh /absolute/path/to/recovery.profile
```

Set `PRELOAD_IMAGES` in a profile to a comma-separated list if a few images should be pulled during initial verification. Image references may contain registry paths, tags, digests, dots, dashes, and underscores. Normal Testcontainers pulls are cached automatically on the persistent disk.

## Daily use

Start the VM in the background:

```bash
./scripts/start-vm.sh ./profiles/dev.profile
```

Run host tests through the guest Docker API:

```bash
./scripts/build-docker-proxy.sh # once, and after proxy source updates
./scripts/run-test-env.sh -- npm test
```

The wrapper supplies `DOCKER_HOST`, `TESTCONTAINERS_HOST_OVERRIDE`, and `TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE` to the test process on both platforms. On Windows it passes them across the MSYS-to-Windows process boundary and restores a writable native temporary directory before launching JVM tests. In a Linux container, the test process runs in the same outer container as QEMU. It keeps Ryuk enabled. Random published ports work when the framework asks Docker to assign a port because guest allocation and host forwards share the configured range.

The default `auto` metrics mode collects host-wide, QEMU-process, and Alpine-guest CPU and memory metrics on Windows, and runs Linux commands without the PowerShell collector. When Windows collection is enabled, only the final average/peak summary is printed and a structured report atomically replaces `~/.qemu-guests/metrics/latest.json`. Linux runs do not produce a metrics summary or update that report. Both platforms preserve the original command exit code. The report intentionally omits the command text and working-directory path. Very short commands can finish before the first sample and therefore produce `null` aggregates.

Other operations:

```bash
./scripts/run-docker.sh -- ps
./scripts/sync-workspace.sh --remote-dir /root/my-project /path/to/project
./scripts/connect-vm.sh               # interactive SSH session
./scripts/connect-vm.sh --sftp        # SFTP session
./scripts/stop-vm.sh ./profiles/dev.profile
```

## Profile settings

- `VM_NAME`, `VM_MEMORY`, `VM_CPUS`, `VM_DISK_SIZE`
- `VM_ACCELERATOR=auto|kvm|whpx|tcg`; `auto` probes KVM on Linux or WHPX on Windows before falling back to TCG. Explicit hardware modes fail if unavailable
- `SSH_PORT` and `DOCKER_DAEMON_PORT`
- `TESTCONTAINERS_PORT_START=20000` and `TESTCONTAINERS_PORT_END=auto` (20127 on both platforms); explicit numeric ranges have no port-count ceiling

- `TESTCONTAINERS_PULL_PAUSE_TIMEOUT` and `TESTCONTAINERS_PULL_TIMEOUT` in seconds; the bundled profile raises both for large image extraction under TCG fallback
- `TESTCONTAINERS_RESOURCE_METRICS=auto|true|false` and `TESTCONTAINERS_RESOURCE_METRICS_INTERVAL=1`; collection requires Windows PowerShell and accepts intervals from 1 to 60 seconds
- `PORT_FORWARD=host:guest,...` for additional fixed loopback forwards
- `ALPINE_BRANCH` and `ALPINE_MIRROR_BASE`; use `auto` for fastest-mirror detection or an explicit `http://`/`https://` base URL to disable detection
- `PRELOAD_IMAGES=image,...`

`auto` computes the end from the configured start plus 127, so a custom start
still gets 128 ports. A pool extending above 65535 must use explicit valid bounds.

The bundled development profile selects acceleration automatically and allocates 4 GiB of guest memory plus four virtual CPUs for multi-container and JVM-based Testcontainers suites.

Fixed host ports must not overlap the Testcontainers range. All forwards bind to `127.0.0.1`.

gvproxy owns forwarded listeners, while QEMU owns one TCP transport connection.
The former Windows QEMU listener warning no longer applies to this backend.
The 128-port default is a configurable allocation pool, not a gvproxy capacity
limit. Explicit pools must lie within `1024–65535`, leave guest outbound ports,
and avoid host forwards/control ports and guest Docker API port 2375. Startup
registers the entire pool in one controller using a persistent HTTP connection;
a failed bind or request aborts and cleans the owned helper, without connection retries.
On Linux the helper inherits enough file descriptors for its listeners plus 256
descriptors of connection headroom. A smaller hard limit requires raising the
host/container `nofile` limit or selecting a smaller pool. Host port availability,
memory, descriptors and concurrent connections still determine practical capacity.
Ryuk stays enabled and shares the pool. All plugin forwards currently use TCP;
UDP/SCTP published ports are not exposed by these scripts. Binding listeners
does not prove application responses or load capacity.

New guests use a Docker startup wrapper that sets the selected pool before each
daemon execution, initializes the cached allocator, then restores the outbound kernel
range to `32768–60999` (or its larger disjoint portion for overlapping custom pools).
If a pool covers that whole interval, it selects the larger disjoint portion of
`1024–65535`; a pool leaving no outbound port is rejected before launch.
On fresh guests, a temporary BusyBox image is imported from guest files, published
once to verify allocation, and removed without a registry pull. Restored published
containers also initialize the allocator, allowing a fully occupied pool to restart.
Startup waits for allocator initialization and outbound restoration before reporting
success; guests lacking the wrapper fail with a maintenance instruction. Docker caches its publish range on first use; leaving the publish range
as the outbound range would make guest outbound connections compete for it.
Daemon failures retain their exit status and OpenRC supervision remains enabled.

Existing persistent guests are not automatically migrated. Keep their explicit
profile range until you can update the guest safely. Changing only the host profile
does not change Docker's cached range; startup rejects a persisted pool mismatch.
During a planned maintenance window, update `/etc/sysctl.d/99-testcontainers-ports.conf`
and install the newly rendered wrapper and `/etc/conf.d/docker` configuration with
the same numeric pool, then restart Docker and QEMU. Preserve custom Docker service
settings when updating that configuration. Restarting Docker interrupts containers;
confirm ownership before doing so. A running VM is never restarted to apply defaults.

## Measured resource reference

On Windows, the proxy follows Docker's Windows archive permissions: it adds execute bits and removes
group/world write permissions so scripts can run in Linux images without Dockerfile workarounds.
In a Linux container, it preserves the source file permission bits; scripts must already have their required execute bits.

A Windows host with 28 logical processors and 31.8 GiB RAM ran a cached Elasticsearch 8.17 Testcontainers integration test through the bundled 4-vCPU, 4-GiB profile with automatic resource collection enabled. `VM_ACCELERATOR=auto` selected WHPX. The wrapper recorded a successful 20-second command, Gradle reported 16 seconds, the test case took 14.89 seconds, and Elasticsearch became ready in 10.41 seconds. The collector produced 13 valid samples with no sampling errors. The VM reached SSH and Docker readiness in 26 seconds from a cold VM start. On the same persistent disk, an earlier TCG run needed about 3 minutes 12 seconds for Elasticsearch startup.

| Scope | CPU average | CPU peak | Memory average | Memory peak |
| --- | ---: | ---: | ---: | ---: |
| Windows host, all activity | 23.8% | 35.0% | 29,145 MiB / 89.4% used | 29,279 MiB / 89.8% used |
| QEMU process | 6.5% | 10.2% | 3,464 MiB working set | 3,472 MiB working set |
| Alpine guest | 44.3% | 71.5% | 1,732 MiB used | 2,967 MiB / 75.6% used |

Host and QEMU CPU percentages are normalized across all host logical processors; guest CPU is normalized across its four virtual CPUs. QEMU and guest CPU averages exclude their initial counter baselines. Guest sampling uses SSH, so the figures include that small measurement overhead. Host-wide memory reflects unrelated applications already running on the measurement machine; use the QEMU working set and guest figures when sizing this VM.

## Validation

```bash
./tests/test-apk-mirror-selection.sh
./tests/test-vm-utils.sh
```

The smoke tests use deterministic command mocks; they do not boot QEMU or use the network.

## VM & Containers status panel

The plugin includes a read-only MCP App for the conversation panel described in the [OpenAI plugin extensions](https://developers.openai.com/plugins/build/extensions). Open **VM & Containers** from a supporting host's thread tabs, or ask to show the QEMU / Docker status. The `qemu_docker_status` tool returns a snapshot and the bundled UI resource.

The panel shows:

- VM name, verified QEMU process state and PID, disk presence, provisioning marker, actual process accelerator when readable, and configured profile CPU/memory limits.
- Live CPU and memory usage for the QEMU host system, verified QEMU process, and Alpine guest. Host/QEMU CPU percentages use all host logical CPUs; guest CPU uses all guest CPUs. QEMU memory is resident memory relative to host RAM. In an outer Linux container, host system figures come from the kernel's system view, not the outer container's cgroup quota.
- Local SSH banner reachability and Docker API ping/version. SSH authentication and guest DNS are not tested.
- All running and stopped Docker containers, image, status (including Docker health text), and published ports, with name/image filtering. Running containers include CPU and memory usage; container CPU uses 100% per core and can exceed 100%. Memory subtracts inactive file cache where available and shows usage against the Docker-reported limit.
- Observation time, probe failures, and warnings when local services respond without a verified QEMU process.

Use **Refresh** for a new snapshot. Optional auto-refresh runs every ten seconds while the panel is visible. An unsuccessful refresh preserves the last snapshot and labels it as stale. An unavailable container list is distinguished from a successfully queried empty list.

Resource samples are collected on refresh and are independent of the test wrapper's Windows metrics reports. Guest sampling reads `/proc/stat` and `/proc/meminfo` over loopback SSH using the existing VM key; it does not install tools, create keys, or write state. Local host/process sampling uses the pinned psutil dependency in the MCP runtime. Plain Python use of `scripts/status.py` needs psutil for those two scopes. Missing permissions, SSH failures, stopped processes, or missing CPU baselines show unavailable values rather than zero. A failed container sample does not hide the container list. To bound refresh work, each snapshot samples at most 32 running containers, with eight concurrent probes; remaining containers are marked unavailable.

### Local MCP runtime

Install [uv](https://docs.astral.sh/uv/) on the Linux/Windows host or inside the Linux container running the VM. The compatibility manifests register `.mcp.json`; the host launches a Python stdio server with pinned dependencies. It must run in the same process and network namespace as QEMU because probes are restricted to `127.0.0.1` and ignore HTTP proxy settings. Opening the panel does not start/stop a VM, provision a disk, install tools, modify state files, or mutate containers. There is no settings extension.

Defaults match `profiles/dev.profile` and `~/.qemu-guests`. For a custom existing VM, set `QEMU_STATUS_PROFILE` to its profile file and use the existing `QEMU_ALPINE_BASE_DIR` override if necessary. Paths should be native absolute paths for the Python runtime; Git Bash/MSYS paths are converted through `cygpath` on Windows. Profiles are parsed as data and never evaluated as shell code. A different active VM lock produces a profile-selection warning.

```bash
uv run --script scripts/status-server.py
# Plain JSON snapshot, useful in hosts without MCP Apps rendering:
python scripts/status.py
```

The panel uses the official MCP Apps JavaScript SDK and `openai/ui` global sidebar and thread entrypoints. Its HTML contains the entire bundled script with no external UI dependencies or direct browser calls to Docker. Native rendering depends on host support. This package is a local stdio integration; it does not deploy or register a remote ChatGPT service. Hardware acceleration depends on the host; mocked capability tests do not establish hardware availability.

### Build and validate

See [DEVELOPMENT.md](DEVELOPMENT.md) for resource collector behavior and focused panel verification.

The checked-in `templates/status-panel.html` is generated from `ui/`. Python and uv are runtime requirements for the MCP server; Node is only needed when rebuilding the UI.

UI builds support native Windows paths. Windows status probes translate Git Bash/MSYS PIDs to native Windows PIDs before verifying QEMU identity and reading the accelerator. Missing processes report stopped; unavailable inspection tools report unknown.

```bash
npm ci --prefix ui
npm run build --prefix ui
npm test --prefix ui
uv run --script tests/test-status.py
# Browser tests against a simulated MCP Apps host:
uv run --script tests/test-status-panel.py
```

The browser test needs Playwright Chromium installed (`uv run --with playwright==1.62.0 playwright install chromium`) or `PLAYWRIGHT_CHROMIUM_EXECUTABLE` pointing to an existing Chromium executable. CI rebuilds the bundle, runs protocol/probe/browser tests, and validates generated Codex packages.

## Linux container workflow

See [container/README.md](container/README.md) for the non-root runtime image, persistent storage, and complete commands. An ordinary container can run QEMU with TCG. On compatible Linux hosts, add `--device=/dev/kvm` and the device's group to enable KVM; neither mode requires `--privileged`, a host Docker socket, or a host-network bridge.

The runtime image normalizes shell, profile, and template line endings so Windows CRLF checkouts can be built and run in Linux containers.

Run the test process and status MCP service in the same outer container as QEMU. Loopback forwards stay inside that network namespace. The guest Docker daemon creates containers using its own Linux kernel; its privileges do not require a privileged outer container. Guest architecture remains x86-64, and KVM requires host/guest architecture compatibility.

## Plugin packaging

`plugin.json` is the portable metadata source. Client manifests and complete skill resources are generated into `me.claude` and `me.codex`; install from those repositories. Source skills use portable frontmatter. Claude routing is stored in `extensions.com.anthropic.claude.skillFrontmatter`, keyed by skill directory, and injected only into generated Claude skills. Codex skill files are copied unchanged.

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

## Network recovery

Use the updated plugin or a matching source checkout for setup, start and stop commands. Until the distribution workflow publishes the update and a new Codex chat loads it, manage the VM with the matching source scripts.

`GVPROXY_QEMU_PORT=19200` and `GVPROXY_API_PORT=19201` are loopback control ports; they must be distinct and outside every forward. Python 3 is required for verified process ownership. `GVPROXY_BINARY` can point to a verified helper installed by `setup.sh`.

If gvproxy exits, stop the VM and start it again. Upstream v0.9.0 accepts one QEMU connection per process, so recovery restarts both processes, re-registers all forwards, and waits for SSH and Docker application responses. It does not reconnect an already-running QEMU automatically. Port conflicts fail startup and remove owned processes. Do not restart a VM used by another session. The API can expose ports and must remain on loopback.

## Improvement feedback

Plugin findings go to [storytellerF/me issues](https://github.com/storytellerF/me/issues). Skills require checking open and closed issues before reporting, using sanitized or synthetic examples, and honoring the user's authorization before posting. Existing reports are reused; unavailable access leaves an unsubmitted draft.

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

`BOOT_TIMEOUT` (SSH readiness, default 300 seconds), `FORCE` (`true` skips graceful
shutdown, default `false`) and `TIMEOUT` (graceful shutdown, default 30 seconds)
are read only from the profile; inherited environment variables do not set them.

Provisioning remains shell orchestration in `create-vm.sh`, using the same Python
state controller for operation leases, global reservations, process registration
and state cleanup. Guest templates and simple command forwarding remain shell.
Unknown process probes, interrupted guards and failed cleanup retain ownership
for inspection. On Windows use Ctrl+C or native Ctrl+Break for graceful
cancellation; Git Bash `kill -TERM` forcibly terminates native Python and cannot
run cleanup. Inspect any remaining operation lease before manual recovery.
After partial PID publication, an owned stop also checks the pending launch PID
and native identity before touching networking or releasing the reservation.
If PID publication is incomplete or identity remains unknown, inspect the retained
state and processes before manual recovery; missing PID files alone do not prove exit.

Failures before QEMU creation, such as an unwritable log or a definite process
creation failure, clean up this launch's helper and reservation automatically.
Initial guard metadata failures also roll back a guard created by that operation,
allowing a retry; pre-existing interrupted guards still require inspection.
Shell clients also retain cleanup responsibility while requesting their lease or
guard. Cancellation waits for the creator to finish, then releases only that
request's resources; failed token delivery can be retried without manual lock removal.
Cancelling helper creation waits for its owned process to exit before removing
its reservation. If exit cannot be confirmed, its recovery evidence remains.
Cancellation before readiness follows the same cleanup when process ownership can
be verified. Once readiness is committed, the VM remains running in the background.
Cancelling a stop preserves remaining ownership so a later stop can finish.
If a native helper controller cannot be confirmed exited, the operation lease
also stays in place; inspect all remaining plugin processes before recovery.
Existing helper ownership is never adopted by a new start; explicitly stop that
VM first. See [developer lifecycle rules](https://github.com/storytellerF/me/blob/main/DEVELOPMENT.md#vm-lifecycle-and-state-controllers)
for phase transitions and recovery evidence.

## Profile configuration isolation

Profile settings come only from the selected literal `KEY=value` file. Missing
required settings fail validation; missing optional settings use built-in defaults.
Each load replaces the previous file configuration. Profile settings are not
exported to child processes; Testcontainers settings are passed explicitly to
the test command where required. Unknown profile keys are rejected, so profiles
cannot change PATH, HOME or controller/tool selection.

Set VM resources, ports, acceleration, Alpine image/mirror settings, image
preloading, lifecycle timeouts, `FORCE` and `VERIFY_EXISTING` in the profile.
Host controls such as `QEMU_ALPINE_BASE_DIR`, `QEMU_STATUS_PROFILE`,
`QEMU_STATE_PYTHON`, `QEMU_BASH_BINARY`, `GVPROXY_BINARY` and proxy helper paths
remain environment settings. They are not profile keys.


Normal startup creates QEMU directly from Python and records its native process
identity before readiness. A completed start transfers ownership to the persisted
VM state so the VM continues running. Interrupted or unverified publication keeps
the reservation and networking for inspection; older shell-launched records remain
recoverable. Do not remove retained state merely because a PID file is absent.

## Guest provisioning dependencies

The Alpine guest installs `docker`, `docker-cli-compose`, and `openssh` for the
Docker API/CLI, Compose commands, SSH/SFTP, and proxy compilation transport.
OpenRC supplies the `cgroups` service; provisioning enables it with
`rc-update add cgroups default`. Do not add the non-Alpine `cgroupfs-mount`
package. Go is installed only when building the Docker CLI proxy. The outer
Linux runtime reads process identity from `/proc` and does not require `procps`.
The guest installer explicitly includes the supervised Docker wrapper in Alpine's
`lbu` archive so its executable and OpenRC configuration survive system installation.

For a real acceptance check, provision a fresh isolated VM with its own
`QEMU_ALPINE_BASE_DIR`, profile ports, disk, key, and proxy output directory.
After starting it and building its proxy, run from this plugin root:

```bash
bash scripts/run-test-env.sh --profile /path/to/isolated.profile -- \
  uv run --script tests/validate-guest-testcontainers.py --pool-start 28000 --pool-end 28015
```

Use the publish-pool bounds from that isolated profile. This opt-in check pulls
BusyBox, Alpine and Ryuk images, exercises HTTP forwarding and CPU/memory cgroup limits,
forces an OOM inside the constrained container, and checks workload removal.
Keep Ryuk enabled. Stop only the isolated VM after verification.

## Experimental Windows GPU patch bundle

The plugin includes a source-only viogpu/VirGL patch bundle for a Windows guest
using native host OpenGL. A patched QEMU can keep its SDL display hidden from
initial creation (`-display sdl,gl=on,hidden=on`) while the guest retains its
interactive desktop for automation. Hidden mode is incompatible with full-screen.
Keep `graphical: true`; this is a hidden graphical backend, not `-display none`.

This is an opt-in developer experiment, not a new managed runtime selector or an
automatic GPU driver installer. Existing profiles and runtime defaults are unchanged.
Use a separate private runtime/profile and retain rollback copies. Driver signing
and guest setup remain operator prerequisites; no host Secure Boot changes are
performed by this bundle. Test compilation stays on the host.

See [build, qualification and rollback instructions](DEVELOPMENT.md#experimental-viogpu-source-bundle).
