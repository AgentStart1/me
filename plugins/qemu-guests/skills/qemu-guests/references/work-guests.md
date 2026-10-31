# Work guest preparation

Apply the shared project, build-placement and ownership rules in SKILL.md. Paths below are relative to the installed plugin root; resolve them before invoking scripts from a consuming project.

## Provision and connect

Use `scripts/guest-vm.py install|run|stop|status|plan <guest.json>`. Guest JSON profiles are distinct from Alpine `.profile` files. Multiple work VMs may run simultaneously, each with an independent state directory, disk, lease and host SSH port. Do not install Docker proxies or backend credentials in work guests; host Docker/Testcontainers remains independent.

Ubuntu uses verified cloud-init images. Windows uses BIOS/MBR amd64 unattended answer files for compatible media. Read the [provisioning instructions](../../../README.md#provision-and-run) for media, runtime archives and exact profile fields; use [custom adapters](../../../README.md#custom-unattended-adapters) for unsupported installers. For Intel macOS, read [macOS preparation](macos.md) before planning or installing.

Prepare Appium with `scripts/build-appium-runtime.py` in a designated preparation environment matching the target OS and CPU architecture. Pin project-required drivers explicitly (Windows desktop example: `--driver appium-desktop-driver@2.8.0`). Supply the archive, checksum and unique host port in the profile's `appium` object. Connect using `scripts/connect-appium.py`; verify the first SSH host-key fingerprint. Windows uses a persistent auto-login test account and an interactive logon task so applications open only on the guest desktop. Stage application artifacts and arrange backend reachability through the consuming project's own test tooling. Never bake project paths, app packages, test commands, credentials or a particular project's SDKs into this plugin.

During preparation, set the JSON `graphical` boolean for desktop components (Ubuntu XFCE/LightDM or Windows Server Desktop Experience versus Core). Give graphical guests distinct loopback-only `qmp_port` values for read-only panel capture. Headless macOS also needs private QMP for Recovery automation. Inspect missing capture support rather than changing a running guest merely to populate the panel.

Validate runtime platform and x64 architecture before new installation; do not infer them from the host OS or accept missing metadata. Preserve existing records: guest-hook fingerprint v2 requires a new isolated initialization for older hook-based environments, while no-guest-hook fingerprints stay compatible. Do not reset disks or patch fingerprints to accommodate changed requirements.

## Windows managed runtime

Windows defaults to four vCPUs and `qemu_runtime: "whpx-reset"` on Windows 11 x64. `install`/`run` build or verify the managed QEMU 11.1.2 runtime, including private DLLs and firmware; only WHPX is compiled. Use Python 3.12+ and MSYS2 UCRT64 (`QEMU_MSYS2_ROOT` for nonstandard host locations). `scripts/whpx_runtime.py` can prepare it ahead of time. `plan`/`status`/`stop` never build. Keep the tested `Westmere,-vmx,-svm` CPU arguments, no explicit `qemu` override and no `install_reboots` cold-boot budget for the managed runtime. On Linux hosts, profiles must select the system runtime and KVM explicitly.

Read DEVELOPMENT.md for managed-runtime provenance, build recovery and verification. The bundled local partition-reset patch adapts an upstream proposal; stock 11.1.2 still failed on the tested host. The CET/XSAVE patch also bounds WHPX CET bits by the selected model and guest XSAVE/XSAVES support; never re-enable host CET on Westmere. Validate actual guest flags as well as boot readiness, and preserve crash disks/RAM privately when investigating init panic. Never replace system QEMU implicitly. Cached runtime files are hashed before execution, and recipe changes create a separate cache.

For runtime implementation or reboot qualification changes, also read [maintenance and validation](implementation-maintenance.md). Runtime readiness is separate from the requested application's test results.

## Ubuntu GPU on Windows

For Ubuntu OpenGL on Windows 11 x64, use the opt-in `virgl-whpx` managed runtime
and `profiles/ubuntu-virgl-whpx.json`. Read the owning README's Ubuntu GPU section.
Build pinned public sources with `scripts/virgl_runtime.py`; never substitute a
cached private experimental binary or overwrite system QEMU. Install a fresh
state directory with the project's portable `--requirements`; do not convert an
existing software disk by changing its profile or fabricate an initialization
receipt. 
The generated GPU session inherits the dedicated Xorg console and preserves its
isolated D-Bus/AT-SPI and temporary unlocked native keyring. Require the current
boot/session receipt, hardware VirGL, actual rendering, native Appium input and
screenshots, then unchanged business acceptance. Require a logged-on host desktop even with hidden
SDL; session 0, logout and host-boot autostart are unqualified. The managed
runtime supports panel QMP capture through an on-demand scanout snapshot;
verify its orientation, colors and current dimensions against native Appium
screenshots. CUDA, Vulkan and video decode are not qualified. Read DEVELOPMENT.md for
source rebuilding, failure regressions and cold-start qualification.

## Experimental Windows viogpu

For the source-only hidden SDL/VirGL experiment, follow the experimental viogpu
section in DEVELOPMENT.md. Verify the pinned bundle with
`scripts/verify-viogpu-bundle.py` before preparing an isolated source/runtime tree.
No new managed runtime name or unattended guest driver install is provided.
Keep guest GPU profiles, signing choices, patched binaries and rollback state
outside consuming projects. Do not change host Secure Boot.
Use the existing test runner's owned temporary Appium transport; hidden display
still requires a logged-on guest desktop. Do not equate SSH readiness, a warm
reboot of an older DLL, or earlier full-suite results with current GPU acceptance.
