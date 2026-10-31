---
name: qemu-guests
description: Use when running desktop application tests, testing in an OS or runtime environment different from the current host, or preparing a Docker environment for tests, including Testcontainers. Coordinate environment selection and test execution internally; users need not request QEMU or Appium. Also use for explicit management, status, or screen inspection of existing QEMU test environments. Exclude ordinary host-local unit tests and Docker work unrelated to testing or these managed environments.
---

# QEMU Guests

## Route the test request

Start from the requested tests and their target environment, not from VM provisioning. Read the project's existing test commands, target OS/architecture, runtime dependencies and configured Docker/Appium endpoints; inspect available environments before selecting a route. Infer requirements from the project and request where possible, and ask only for missing information that changes the target or prevents execution. Skill activation does not by itself require creating a VM.

- For desktop tests, reuse a suitable designated desktop test environment. When an isolated guest is needed, select a supported work guest and coordinate its desktop, Appium connection and artifact transfer using the selected reference below.
- For tests targeting an environment different from the current host, reuse a matching existing environment or prepare a supported guest. Preserve the requested OS, architecture and runtime; report unsupported targets or missing prerequisites instead of silently substituting the host or another guest.
- For tests requiring Docker or Testcontainers, reuse a suitable configured Docker endpoint. Use Docker directly on ordinary Linux hosts; prepare the independent Alpine backend on supported Windows or Linux-container hosts when a backend is needed. Docker-only tests do not require a desktop guest.
- When tests require both a desktop guest and Docker services, coordinate them independently through the host test execution reference below and run the project's existing tests with standard endpoints and portable configuration.

The skill owns selection of provisioning, runtime preparation, connection, execution and cleanup procedures; do not make users name these mechanisms to activate it. Respect an explicitly chosen environment. Check the actual requested test results before reporting success; a ready VM, desktop, Appium server or Docker daemon is only environment readiness. For explicit VM lifecycle, status or screen requests, perform that operation without adding a test run or provisioning unrelated resources.

## Project independence and paths

Keep this AI plugin's launcher paths, VM/backend profiles, credentials and lifecycle procedures outside consuming projects. Projects declare portable artifact/service roles and standard Docker/Appium requirements; do not add QEMU/AI-plugin-specific runtime branches or documented helper invocations merely to run tests. Return native diagnostics through the application-side service instead of making clients detect the VM provider. Required Appium drivers/extensions, Gradle plugins and other real project dependencies must still be declared and documented. Explicitly requested provider integration is limited to that requested scope.

Resolve the installed plugin root from this skill's location (`<plugin-root>/skills/qemu-guests/SKILL.md`). Invoke helpers by absolute path while preserving the consuming project's working directory. Script/profile paths in the references are relative to that plugin root; copy private profiles outside the checkout. No other installed skill is required for these boundaries.

## Common execution rules

- Work VMs are runtime/test environments. Compile applications, test code, native dependencies and installation hooks on the host or a designated preparation environment unless the user explicitly requests work-guest compilation. Runtime setup or a test request does not grant that permission. Do not silently install build tools in the work guest or increase its resources to accommodate a build. Ordinary runtime JIT execution is not a build step. The Alpine backend's Docker CLI proxy build is a separate, documented tooling operation.
- Reuse suitable initialized environments for ordinary tests. Qualifying a new installation requires independent state directories, disks and ports; never reset an existing VM to validate an installer. Keep media, account credentials, SSH keys, seeds, runtime archives and diagnostic logs private.
- Verify native process identity and ownership before stopping anything. Do not bypass active leases or clear uncertain state, guards, sessions or reservations. A missing PID file, SSH disconnect or readiness marker alone does not prove process exit or successful cleanup. Retain evidence and inspect the affected resources before recovery.
- Keep forwards and control endpoints on loopback. Preserve other guests and the independent backend. Keep a work guest's foreground supervisor alive; use another terminal for status or stop.
- Honor the requested accelerator and runtime. Managed work-guest build, checksum or accelerator failures are terminal; never silently substitute TCG. Only the Alpine backend's automatic acceleration policy permits its documented fallback.
- Ensure the desktop fits the suite's windows at the configured DPI before testing; do not change geometry or compete with manual console use during a run. A ready SSH/Appium endpoint is not proof of a working or unlocked desktop or of a passing application test.
- On Windows, use Ctrl+C or native Ctrl+Break for graceful cancellation of Python controllers. Git Bash `kill -TERM` can bypass cleanup; inspect retained ownership after forced termination. Append fallback MSYS2 tool directories to PATH so existing tool choices retain priority.

## Read only the relevant workflow

| Task | Required guidance |
| --- | --- |
| Prepare/install a Windows or Ubuntu work guest, configure Appium, or select a GPU runtime | [Work guest preparation](references/work-guests.md) |
| Install Intel macOS or prepare/recover its Appium desktop or GPU runtime | [Intel macOS preparation](references/macos.md) plus common [work guest preparation](references/work-guests.md#provision-and-connect) |
| Initialize portable project runtime requirements, execute host-driven tests, or collect results | [Host-driven test execution](references/test-execution.md) |
| Provision/use the independent Alpine Docker backend or build its CLI proxy | [Alpine Docker backend](references/docker-backend.md) |
| Change Alpine profiles, ports, metrics or recover retained backend state | [Configuration and recovery](references/configuration-and-recovery.md) |
| Change plugin lifecycle/runtime/transport code or perform plugin regression validation | [Implementation and validation](references/implementation-maintenance.md) |

Read the selected guidance before acting; do not load unrelated platform procedures or run maintenance checks as part of an ordinary test request. For supported media, profiles and user-facing commands, follow the linked sections of the [plugin README](../../README.md). Use [DEVELOPMENT.md](../../DEVELOPMENT.md) for implementation evidence and qualifications rather than treating historical experiments as current compatibility guarantees.

## Read-only status and screens

For requests to view VM state, service health, or containers, call `qemu_docker_status` to open **VM & Containers** in hosts supporting MCP Apps. It has an `openai/ui` global sidebar and thread entrypoints and takes no arguments. The global entrypoint adds a left-sidebar launch item; the thread entrypoint opens it beside a conversation. Refresh remains within the panel. Never start a VM or provision resources merely to populate this view.

Without MCP Apps support, run `scripts/status.py` with Python 3 and summarize its JSON snapshot. Read `QEMU_STATUS_PROFILE` for a custom profile and `QEMU_ALPINE_BASE_DIR` for existing state overrides; do not invent a running state from the ready marker. Unknown probes, unavailable lists, and stale PID files must be reported as such. SSH health means a banner was received, not successful authentication. Resource counts and accelerator policy are profile configuration, not measured utilization. The separate accelerator field is read from the running process when available.

The separate `resources` snapshot reports live host-system, QEMU-process, and Alpine-guest CPU/memory; each container's `resources` reports CPU/memory when running. These are refresh samples, not the test wrapper's metrics report. Host/QEMU CPU is normalized over host logical CPUs; guest CPU is normalized over guest CPUs; container CPU uses 100% per core. Linux host-system values reflect the kernel system view, not an outer container's cgroup allocation. Preserve unavailable and not-running states and null CPU baselines. Guest sampling uses only the existing key and fixed read-only `/proc` commands over loopback SSH. Never create keys or install guest tools to populate the panel. The MCP runtime includes psutil; plain Python needs it for host/process samples. Container probes are bounded to 32 running containers with eight workers.

The panel lists registered work VMs and shows available live read-only screens; it never sends keyboard/mouse input. `qemu_guest_screen` is app-only and accepts a registered guest ID, verifying native identity and QMP listener ownership. Ordinary snapshots contain no image data; temporary capture files are removed. Configure graphical/QMP support during guest preparation, not in response to a read-only status request.

Use `scripts/guest-vm.py status <guest.json>` for an individual work guest. The panel is read-only; manual interactive testing needs a separate console. For a status/screen request, do not install tools, generate keys or start a test merely to fill missing data.

## Finish the requested work

Report the actual environment and test result, relevant artifact locations, skipped or unsupported checks, and any retained resources requiring inspection. Distinguish environment readiness from application acceptance. Stop only requested or owned temporary resources, preserving reused services and uncertain ownership. Downloads, provisioning and startup must be within the request or prior authorization; do not ask again for already authorized steps.

## Upstream improvement feedback

- Report actionable plugin bugs or reusable improvements to [storytellerF/me](https://github.com/storytellerF/me/issues), identifying the plugin and skill. Exclude project-only problems without evidence of a plugin defect. Finish the primary task before non-blocking feedback work.
- Before searching or posting, reduce evidence to a minimal privacy-safe summary or synthetic reproduction. Never disclose raw conversations, private code, logs, screenshots, credentials, personal/account data, or private paths/URLs. Keep findings local if safe disclosure is impossible.
- Search open and closed issues and read likely matches and resolutions. Reuse matching reports; a distinct regression or uncovered case may need a linked new issue. Posting a new issue or a materially useful comment requires existing user authorization; this rule grants none. Without authorization, prepare an unsubmitted draft.
- Include the plugin/skill version, observed and expected behavior, reproduction or proposal, and duplicate-search results; prefix new issue titles with the plugin name. On access or submission failure, retain the draft and explain the blocker. After an uncertain submission, check whether it succeeded before retrying. Return the report link or clearly label the draft as unsubmitted.
