# Configuration and Recovery

## Profiles and ports

Profiles are literal `KEY=value` files and must not contain shell expansion. Required network settings are:

- `SSH_PORT`
- `DOCKER_DAEMON_PORT`
- `TESTCONTAINERS_PORT_START`
- `TESTCONTAINERS_PORT_END`

The bundled end value `auto` resolves to 20015 on Windows and 20255 on Linux,
starting at 20000. Explicit numeric ranges retain the 512-port ceiling. The gvproxy backend registers SSH, Docker API, the full range and custom
`PORT_FORWARD=host:guest,...` mappings through its services API. These mappings must be unique and must not overlap reserved ports.

New guests initialize Docker's cached publish pool with the same numeric range
and restore a broad, disjoint kernel outbound range after readiness. Existing
disks retain their configured publish pools; see the plugin-root README for compatibility and
restart requirements. Do not restart a VM owned by another session.

Control ports `GVPROXY_QEMU_PORT` (19200) and `GVPROXY_API_PORT` (19201) are loopback-only and may not overlap forwards. Recovery requires a coordinated stop/start of both QEMU and gvproxy; rules are regenerated from the profile.

## Acceleration and provisioning

`VM_ACCELERATOR=auto` probes KVM on Linux or WHPX on Windows, otherwise selecting TCG. Set `kvm` or `whpx` to require that accelerator; unavailable explicit accelerators fail instead of falling back. KVM uses `host`, WHPX uses `qemu64`, and TCG uses `max`. KVM requires a compatible x86-64 host and access to `/dev/kvm`; in a Linux container, map that device and grant its group to the container user, without privileged mode. See the plugin-root `container/README.md` for commands.

`ALPINE_MIRROR_BASE=auto` selects the fastest official-list mirror during first provisioning, requires the automatically selected mirror to work over HTTPS, and falls back to the official HTTPS CDN. Set an explicit HTTP(S) base URL to disable automatic selection.

`PRELOAD_IMAGES` optionally pulls a comma-separated image list during provisioning. Registry paths, tags, digests, dots, dashes, and underscores are accepted. Otherwise, Testcontainers pulls once and Docker reuses the layers from the persistent disk.

## Metrics

`TESTCONTAINERS_RESOURCE_METRICS=auto` enables one-second Windows sampling by default and skips the Windows collector on Linux. Explicit `true` requires Windows PowerShell. Change the interval with `TESTCONTAINERS_RESOURCE_METRICS_INTERVAL=1` (1-60 seconds), or disable collection when PowerShell is unavailable. The latest JSON report is stored below the VM base directory at `metrics/latest.json`; it records timings and aggregate resource values but not the test command or working-directory path.

## Limitations and recovery

Setup, lifecycle and client scripts share an operation lease. Competing calls fail before modifying the VM. Normal exits and handled signals release the lease. After a forced kill, inspect all plugin processes before removing interrupted `run/vm-operation.lock`, `vm-state.guard` or helper `.control.lock` directories. Never discard QEMU/gvproxy identity records while either owned process remains alive.

Because Docker runs in a remote guest, Host or outer-container paths cannot be used as ordinary Docker bind mounts. Prefer Docker build contexts, named volumes, or test fixtures copied through the Docker API.

If provisioning leaves a disk without a ready marker, inspect the install and verify console logs. When installation is known to be complete and only verification failed, run `VERIFY_EXISTING=true ./scripts/create-vm.sh <profile>` to resume verification. Do not remove the VM directory unless the user explicitly chooses to rebuild it.
