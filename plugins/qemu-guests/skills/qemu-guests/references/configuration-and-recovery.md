# Configuration and Recovery

## Profiles and ports

Profiles are literal `KEY=value` files and must not contain shell expansion. Required network settings are:

- `SSH_PORT`
- `DOCKER_DAEMON_PORT`
- `TESTCONTAINERS_PORT_START`
- `TESTCONTAINERS_PORT_END`

Lifecycle options are read only from the selected profile, never inherited from
the process environment. Missing optional values use the defaults below.
`BOOT_TIMEOUT` is the SSH readiness timeout in seconds (default 300).
`FORCE=true` skips graceful shutdown (default `false`), and `TIMEOUT` bounds the
graceful shutdown wait in seconds (default 30).

The end value `auto` selects 128 ports from the configured start on both platforms
(20000–20127 by default). An automatic pool extending above 65535 is rejected;
explicit numeric ranges have no count ceiling. The guest kernel
requires a pool within 1024–65535 and the plugin requires remaining outbound space.
The pool must also exclude guest Docker API port 2375, even when its host port differs.
The gvproxy backend registers SSH, Docker API, the full TCP range and custom
`PORT_FORWARD=host:guest,...` mappings through its services API. These mappings must be unique and must not overlap reserved ports.

Registration completes before QEMU starts, using one connection without retries.
Any failure cleans the owned helper and partial rules. Linux helper file descriptor
limits must cover all listeners plus connection headroom; startup reports an
insufficient hard limit. UDP/SCTP publishing is not forwarded. See the README for
resource constraints and maintenance of existing guests with smaller explicit pools.

New guests initialize Docker's cached publish pool with the same numeric range
and restore a broad, disjoint kernel outbound range after readiness. Existing
disks retain their configured publish pools; see the plugin-root README for compatibility and
restart requirements. Do not restart a VM owned by another session.

Control ports `GVPROXY_QEMU_PORT` (19200) and `GVPROXY_API_PORT` (19201) are loopback-only and may not overlap forwards. Recovery requires a coordinated stop/start of both QEMU and gvproxy; rules are regenerated from the profile.

## Acceleration and provisioning

`VM_ACCELERATOR=auto` probes KVM on Linux or WHPX on Windows, otherwise selecting TCG. Set `kvm` or `whpx` to require that accelerator; unavailable explicit accelerators fail instead of falling back. KVM uses `host`, WHPX uses `host`, and TCG uses `max`. KVM requires a compatible x86-64 host and access to `/dev/kvm`; in a Linux container, map that device and grant its group to the container user, without privileged mode. See the plugin-root `container/README.md` for commands.

`ALPINE_MIRROR_BASE=auto` selects the fastest official-list mirror during first provisioning, requires the automatically selected mirror to work over HTTPS, and falls back to the official HTTPS CDN. Set an explicit HTTP(S) base URL to disable automatic selection.

`PRELOAD_IMAGES` optionally pulls a comma-separated image list during provisioning. Registry paths, tags, digests, dots, dashes, and underscores are accepted. Otherwise, Testcontainers pulls once and Docker reuses the layers from the persistent disk.

## Metrics

`TESTCONTAINERS_RESOURCE_METRICS=auto` enables one-second Windows sampling by default and skips the Windows collector on Linux. Explicit `true` requires Windows PowerShell. Change the interval with `TESTCONTAINERS_RESOURCE_METRICS_INTERVAL=1` (1-60 seconds), or disable collection when PowerShell is unavailable. The latest JSON report is stored below the VM base directory at `metrics/latest.json`; it records timings and aggregate resource values but not the test command or working-directory path.

## Limitations and recovery

Setup, lifecycle and client scripts share an operation lease. Competing calls fail before modifying the VM. Normal exits and handled signals release the lease once owned controller exit is confirmed; an unjoinable native controller retains it to block late publication. After a forced kill or failed controller cancellation, inspect all plugin processes before removing interrupted `run/vm-operation.lock`, `vm-state.guard` or helper `.control.lock` directories. Never discard QEMU/gvproxy identity records while either owned process remains alive.

An owned stop can recover a partially published QEMU launch from its pending PID
or native identity even when the per-VM PID file is missing. Failed identity
inspection, an unidentifiable live process, conflicting PID pointers, or a launch
whose PID publication never completed retain networking and the VM reservation
for inspection. Do not remove the reservation merely because a PID file is absent.

Definitive failures before QEMU creation (including log access and process creation
errors) clean up the current launch automatically. If start is cancelled before
readiness, its verified process and helper are stopped; a committed ready VM stays
running. A cancelled stop retains remaining ownership for another stop to finish.
Existing helper ownership requires an explicit stop and is not adopted by start.
For recovery, inspect the atomic `run/active-vm.lock/lifecycle.json` phase and
process evidence together with native identities; do not edit phases or delete
records to bypass an unknown launch. Developer transition rules are in DEVELOPMENT.md.

Because Docker runs in a remote guest, Host or outer-container paths cannot be used as ordinary Docker bind mounts. Prefer Docker build contexts, named volumes, or test fixtures copied through the Docker API.

If provisioning leaves a disk without a ready marker, inspect the install and verify console logs. When installation is known to be complete and only verification failed, set `VERIFY_EXISTING=true` in a recovery profile and run `./scripts/create-vm.sh <recovery-profile>` to resume verification. Do not remove the VM directory unless the user explicitly chooses to rebuild it.
