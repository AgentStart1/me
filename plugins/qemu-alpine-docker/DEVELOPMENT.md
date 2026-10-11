# QEMU status panel development

Port configuration tests run without QEMU or guest access:

```bash
bash ./tests/test-port-ranges.sh
./tests/test-vm-utils.sh
./tests/test-linux-testcontainers.sh
```

The port suite covers platform defaults, explicit 512-port compatibility,
gvproxy mappings including controls/custom forwards, duplicate
and reserved ports, outbound range separation, Docker cache initialization and
daemon exit status. Its daemon lifecycle uses mocks; it does not prove a particular
QEMU binary's socket capacity or replace fresh Alpine/OpenRC provisioning validation.
The startup wrapper remains under Alpine's stock OpenRC supervisor through
`DOCKERD_BINARY`, so restarts/respawns seed the pool before every daemon execution.
Its readiness check uses the guest Unix socket, independent of host forwarding.
The cache behavior follows [Moby's allocator initialization](https://github.com/moby/moby/blob/v28.5.1/libnetwork/portallocator/portallocator.go);
the binary override follows [Alpine's OpenRC service](https://gitlab.alpinelinux.org/alpine/aports/-/blob/master/community/docker/docker.initd).
API readiness alone does not force lazy allocator initialization. A fresh guest
imports BusyBox plus its musl loader from local files, briefly publishes a container,
checks the automatic port, then removes its own container/image. Restored mappings
already initialize the allocator; no extra pool port is required in that case.
The guest readiness marker is written after outbound restoration and cleared on
wrapper exit; host startup/provisioning wait for it when the wrapper is installed.

gvproxy v0.9.0 is pinned with upstream SHA-256 hashes. Source verification uses [the release](https://github.com/containers/gvisor-tap-vsock/releases/tag/v0.9.0), `cmd/gvproxy/config.go`, `cmd/gvproxy/main.go`, and `pkg/virtualnetwork/services.go`. The QEMU socket uses guest `192.168.127.2`, gateway/DNS `.1`, host alias `.254`, and fixed guest MAC `5a:94:ef:e4:0c:ee`. The services endpoint is `/services/forwarder/{expose,unexpose,all}`. Startup validates control/forward collisions and verifies native PID executable plus creation time before cleanup. No QEMU `hostfwd` remains. Launch includes `-ssh-port -1` to disable upstream's implicit 2222 rule; SSH is registered through the API with the profile's other forwards.

Upstream's QEMU accept runs once. Test recovery by stopping both processes, starting both, confirming registered rules and first/middle/last application responses. This also avoids silently reconnecting a VM owned by another user. Readiness polling is limited to startup; protocol probes do not retry failed connections. Windows TCP transport must be validated on actual QEMU; upstream README examples are labelled Linux/macOS.

The operation lease spans lifecycle and client commands, preventing stop/reconfiguration while tests, SSH/SFTP, sync or proxy compilation use the guest. Migration retains its lease across nested stop/start; arbitrary client children cannot reuse it for shutdown. Provisioning retains the singleton reservation between install and verification. INT/TERM exit through one EXIT cleanup, and shutdown retains ownership state on incomplete cleanup. QEMU ownership includes native executable, start time and VM name; Windows holds a native process handle and Linux uses pidfds while signalling. Helper records use exclusive reservation, atomic replacement, generation tokens and a controller guard; readiness verifies listener ownership. Interrupted guards require inspection rather than automatic takeover. Setup participates in serialization and derives a missing public key from its existing private key instead of replacing credentials.

Readiness budgets count actual elapsed time, including probe execution. Loopback HTTP calls bypass proxies explicitly and have per-request deadlines; shared SSH calls enable server-alive checks so a lost guest connection cannot keep an operation lease indefinitely.

The resource collector is separate from test-run metrics. `scripts/status_resources.py`
samples the local system and verified QEMU process through psutil, reads guest counters
using `templates/guest-resource-sample.sh` and the existing SSH key, and derives container
usage from Docker's non-streaming stats endpoint. Every sample has an explicit state;
missing CPU deltas remain null. Container memory subtracts cgroup v1 `total_inactive_file`
or cgroup v2 `inactive_file`, matching Docker's Linux CLI convention. Probe failures
remain scoped to the resource sample and never replace a valid inventory.

`ui/host.mjs` owns immutable snapshots, filtering, refresh coordination and lifecycle
cancellation independently of the DOM. The application injects serial coordination,
tool IO, timer and clock dependencies. Blocking resource IO and CPU sampling run in
the Python MCP server, not the browser event loop. `ui/panel.mjs` adapts Host state to
the view; `ui/view.mjs` formats values. Rebuild `templates/status-panel.html` after UI edits.

From the plugin root:

```bash
npm run build --prefix ui
npm test --prefix ui
uv run --script tests/test-status.py
uv run --script tests/test-status-panel.py
```

The browser suite uses a simulated MCP Apps host and covers resource rendering,
unavailable values, stale snapshots, responsive layout and refresh. Set
`PLAYWRIGHT_CHROMIUM_EXECUTABLE` to an installed Chromium executable if Playwright's
own Chromium is unavailable. It does not establish hardware acceleration or real
guest/cgroup availability; validate those with an already-running VM separately.

Real helper lifecycle/API verification (no guest):

```bash
GVPROXY_BINARY=/path/to/verified/gvproxy python tests/test-gvproxy-lifecycle.py
GVPROXY_BINARY=/path/to/verified/gvproxy python tests/test-vm-lifecycle.py
```

The second fixture runs real bare QEMU and gvproxy without guest disks, with mocked guest IO. It tests competing start/stop/create/migrate, nested migration, healthy idempotency, TERM/timeout cleanup, client-child shutdown refusal, command exit preservation and an unchanged sentinel disk. Set `QEMU_TEST_BINARY` and `BASH_TEST_BINARY` for non-default installations. CI installs QEMU and runs both fixtures on Linux.

For application verification on an idle, already-running Windows VM with Go and cached `postgres:11-alpine`:

```bash
uv run --script tests/validate-gvproxy-network.py
```

This opt-in probe requires the default loopback SSH/API/control ports. It registers 70 same-port HTTP forwards (21000–21069), checks all responses three times, and performs 320/640 PostgreSQL connections at concurrency 8/16 without connection retries. It accepts matching pre-registered profile rules for restart verification. It cleans only its own fixtures and extra rules. Run ordinary/custom-network container DNS probes separately. The Linux runtime image contains the verified helper so its unprivileged, network-disabled smoke test needs no download. CI exercises the real helper lifecycle and port-range suites.

Validated migration evidence (Windows x86-64, upstream gvproxy v0.9.0 and installed QEMU 11.0.1): the existing disk boots with WHPX, DHCP selects `.2`/gateway `.1`, guest DNS and both ordinary/custom Docker-network DNS succeed, and the unauthenticated Docker API responds through loopback. With 91 simultaneous rules, all 70 HTTP ports respond in three rounds (210/210), including first/middle/last ports. PostgreSQL reconnect probes pass 320/320 at concurrency 8 and 640/640 at concurrency 16. The same results pass after coordinated QEMU/gvproxy restart with rules restored from the profile. No connection failure retries are added.

The Windows Docker CLI proxy passes its guest Go tests and native build, and builds the Linux runtime image. Its non-root, capability-free, network-disabled TCG smoke test passes with verified gvproxy preinstalled. The real helper and QEMU lifecycle fixtures pass on both Windows and Linux; Linux restart checks cover TIME_WAIT reuse without weakening Windows bind exclusivity. Shutdown refuses a live lifecycle/client lease. Existing shell utilities (131 assertions), status (16 cases), panel and UI Host (5 cases) suites pass, along with portable/client package validation and package-generation/CLI/workflow tests. PostgreSQL readiness waits for the final container-local TCP server, excluding the image's temporary Unix-only init server. Fresh ISO provisioning, actual KVM availability and Linux arm64 execution were not exercised in this migration; keep those distinct from validated existing-disk and x86-64 runtime behavior.

Downstream server verification completes after plugin/runtime checks: three focused cases pass, then the full suite passes 175 tests (174 passed, zero failures/errors, one existing skip), with JDK 21 and unchanged assertions/timeouts. The full command takes 1247 seconds including image tasks.
