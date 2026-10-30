# Intel macOS preparation and recovery

Read the [macOS installation requirements](../../../README.md#unattended-intel-macos-installation) before provisioning. Apply the shared build-placement and ownership rules in SKILL.md; select only the sections below needed for installation, Appium, GPU use or desktop recovery.

## Installation and media

Intel macOS uses prepared Apple installer media and a bootstrap product package: bounded OCR waits for Recovery, keyboard automation opens Terminal, and the attached script invokes `startosinstall` on the explicitly configured empty guest disk (matched by serial when selected). The package postinstall hook explicitly loads first boot on the running target only. First boot configures the user, existing SSH access-group membership, per-user setup preferences and Appium per-user LaunchAgent, preconfigures the standard emulated USB keyboard as ANSI, clears the installer’s one-time auto-login flag before enabling persistent automatic login, then reboots. Build the private product package and ISO with the macOS preparation scripts. Do not claim Apple Silicon IPSW or arbitrary release compatibility. Custom systems still need explicit automation/acceptance. Do not substitute installer clicking for unattended installation; report missing prerequisites precisely.

Apple Recovery images can be downloaded on Windows with OpenCore's macrecovery tool and verified against Apple's signed chunklist; an existing Mac is not required for downloading Recovery. Distinguish this from the full installer app/ISO and private product package required by the current adapter. The macOS example now explicitly selects WHPX, but its CPU arguments and private OpenCore/firmware remain release-specific.

Historical Sonoma/CPUID-cache and Mac2 probes are recorded in [development evidence](../../../DEVELOPMENT.md#experimental-macos-recovery-on-whpx). They do not establish compatibility for another release or an entirely unattended source-adapter run. Do not substitute those experimental binaries for a managed runtime, silently fall back to TCG, or report a Recovery download as a completed installation.

Use a GPT installer disk (GPTSPUD in the preparation helper), attached read-only through USB; do not treat a partitioned Apple image as an ISO9660 CD. Configure OpenCore to boot the installer/target automatically and hide its own EFI self-entry. Resolve the actual Recovery mount path for startosinstall and the explicitly empty target disk; prefer a configured QEMU disk serial because BSD disk numbers can change between boots. Host-side OCR uses the pinned Pillow dependency to enlarge frames before strict prompt matching. Generated shell seeds must retain LF on Windows.

First boot requires FileVault off, publishes dedicated-account loginwindow credentials with root-only permissions, installs the Appium LaunchAgent and reboots. Never disable encryption to satisfy setup. Acceptance must confirm authenticated SSH, the expected console user, its loaded Appium service and ready loopback endpoint. A handoff marker is not installation success; retain it and inspect failures rather than repeating a destructive command.

On Sequoia, a retained `/var/db/.AppleSetupTermsOfService` cookie can force the
Terms pane even when `.AppleSetupDone` and persistent automatic login exist.
The first-boot template clears this separate cookie for the installation already
invoked with `--agreetolicense`. Do not substitute clicking the Terms pane for
validating the corrected bootstrap on an independent empty disk.

## Appium and display prerequisites

Mac2 UI sessions require compatible full Xcode, a prepared WebDriverAgentMac build and Accessibility permission for the built runner and Xcode Helper. Command Line Tools alone is insufficient. Obtain explicit guest-build authorization before allowing Mac2 to invoke xcodebuild; otherwise use a designated build environment and prebuilt WDA endpoint. Validate a real native session/source/screenshot/click separately from server readiness. On macOS without a selected developer toolchain, preserve the launcher’s missing-tool handling so the optional Git revision probe cannot open a developer-tools installer. Never install build tools just to satisfy that probe.

Basic macOS framebuffers may expose only the boot-selected mode; set the private OpenCore UEFI Output Resolution when necessary, retain its original configuration, restart and verify the actual mode. macOS can disconnect SSH before kernel shutdown completes; do not treat that disconnect alone as proof of completed shutdown; wait for the guest to finish before forcing the owned QEMU process to exit.

## Managed GPU runtime

For the qualified Windows 11 x64 / Intel macOS 15.8.1 GPU path, use the bundled
`qemu_runtime: "reims-whpx"` profile and `scripts/reims_runtime.py`, not cached
private experimental binaries or sibling source checkouts. This runtime is
separate from Windows guests' `whpx-reset`. Its dependency pins and patches live
in `patches/reims-windows`; first use builds public sources with GNU Rust and
MSYS2 UCRT64 and verifies the complete runtime. Use
`uv run scripts/prepare-macos-gpu-boot.py` to create a new operator-owned EFI
copy with the bundled, guarded timing fix and pinned Lilu; require build 24H32.
Do not modify a running boot image, overwrite firmware, bypass a failed driver
hash/build guard, or claim support for a new macOS release. Read the [GPU prerequisites](../../../README.md#windows-macos-gpu-runtime) and [driver build instructions](../../../DEVELOPMENT.md#bundled-windows-macos-gpu-dependencies) for the designated preparation machine. Require actual clock/framebuffer and unchanged
business acceptance; native SDL presentation and video decode are unqualified.
Use one normal in-guest shutdown request for cold-boot qualification and confirm
native exit before relaunching; do not race ACPI and SSH shutdown requests.
For application tests, use the macOS transport boundary in [host-driven test execution](test-execution.md); the GPU runtime does not add a transparent `java-argfile` relay.

## Prepared desktop recovery

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
