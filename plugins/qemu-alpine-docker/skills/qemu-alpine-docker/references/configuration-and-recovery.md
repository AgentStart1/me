# Configuration and Recovery

## Profiles and ports

Profiles are literal `KEY=value` files and must not contain shell expansion. Required network settings are:

- `SSH_PORT`
- `DOCKER_DAEMON_PORT`
- `TESTCONTAINERS_PORT_START`
- `TESTCONTAINERS_PORT_END`

The range may contain at most 512 ports. Additional `PORT_FORWARD=host:guest,...` mappings must not overlap reserved ports.

## Acceleration and provisioning

`VM_ACCELERATOR=auto` probes WHPX on Windows and uses it when available, otherwise selecting TCG. Set `whpx` to require hardware acceleration or `tcg` for portable software emulation. WHPX uses `qemu64`; TCG uses `max` so current x86-64-v2 container images are supported.

`ALPINE_MIRROR_BASE=auto` selects the fastest official-list mirror during first provisioning, requires the automatically selected mirror to work over HTTPS, and falls back to the official HTTPS CDN. Set an explicit HTTP(S) base URL to disable automatic selection.

`PRELOAD_IMAGES` optionally pulls a comma-separated image list during provisioning. Registry paths, tags, digests, dots, dashes, and underscores are accepted. Otherwise, Testcontainers pulls once and Docker reuses the layers from the persistent disk.

## Metrics

`TESTCONTAINERS_RESOURCE_METRICS=true` enables one-second sampling by default. Change the interval with `TESTCONTAINERS_RESOURCE_METRICS_INTERVAL=1` (1-60 seconds), or disable collection when PowerShell is unavailable. The latest JSON report is stored below the VM base directory at `metrics/latest.json`; it records timings and aggregate resource values but not the test command or working-directory path.

## Limitations and recovery

Because Docker runs in a remote guest, Windows host paths cannot be used as ordinary Docker bind mounts. Prefer Docker build contexts, named volumes, or test fixtures copied through the Docker API.

If provisioning leaves a disk without a ready marker, inspect the install and verify console logs. When installation is known to be complete and only verification failed, run `VERIFY_EXISTING=true ./scripts/create-vm.sh <profile>` to resume verification. Do not remove the VM directory unless the user explicitly chooses to rebuild it.
