#!/bin/bash
# Shared utilities for the QEMU Alpine Docker plugin.
#
# This file is the foundation of the entire plugin — every script sources it.
# It provides:
#   - Path resolution (scripts, plugin root, home, VM/image/run dirs)
#   - Platform detection (Linux/macOS/Windows via MSYS2/Cygwin)
#   - QEMU binary resolution and acceleration configuration (WHPX on Windows, TCG fallback)
#   - SSH key management, SSH/Docker API wait helpers
#   - Template rendering with placeholder validation (no shell expansion)
#   - VM state management: per-VM PID files + a global singleton lock with a
#     separate state-guard mutex to prevent race conditions between concurrent scripts
#   - Network device value builder that assembles QEMU user-mode port forwarding
#
# Directory layout under $QEMU_ALPINE_BASE_DIR (~/.qemu-alpine-docker):
#   images/     — downloaded Alpine ISO images and checksums
#   vms/<name>/ — per-VM persistent state (disk.qcow2, kernel, initramfs, logs, ready marker)
#   run/        — runtime state:
#       active-vm.lock/   — global singleton lock (directory = mutex; files: qemu.pid, launcher.pid, vm-name)
#       vm-state.guard/   — short-lived mutex protecting lock acquisition/release sequences
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
# Resolve home directory; on Windows/MSYS2, prefer USERPROFILE via cygpath
HOME_DIR="${HOME:-/home/$(id -un)}"
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
        if [ -n "${USERPROFILE:-}" ] && command -v cygpath >/dev/null 2>&1; then
            HOME_DIR="$(cygpath -u "$USERPROFILE")"
        fi
        ;;
esac
# Base directory for all VM state; override via QEMU_ALPINE_BASE_DIR environment variable.
VM_BASE_DIR="${QEMU_ALPINE_BASE_DIR:-${HOME_DIR}/.qemu-alpine-docker}"
IMAGES_DIR="${VM_BASE_DIR}/images"      # Downloaded Alpine ISOs and checksums
VM_DIR="${VM_BASE_DIR}/vms"             # Per-VM directories (disk, kernel, logs)
RUN_DIR="${VM_BASE_DIR}/run"            # Runtime state (locks, metrics stop files)
ACTIVE_LOCK_DIR="${RUN_DIR}/active-vm.lock"  # Global singleton lock — only one VM may run at a time
STATE_GUARD_DIR="${RUN_DIR}/vm-state.guard"  # Short-lived mutex protecting lock acquisition/release
SSH_KEY="${VM_BASE_DIR}/id_ed25519"     # Ed25519 key pair used for all guest SSH connections

# Returns a short tag for the current platform. Used by scripts to branch
# platform-specific behavior (e.g., WHPX acceleration, path conversion).
platform_tag() {
    case "$(uname -s)" in
        Linux*) echo "linux" ;;
        Darwin*) echo "mac" ;;
        MINGW*|MSYS*|CYGWIN*) echo "win" ;;
        *) echo "unknown" ;;
    esac
}

is_windows() { [ "$(platform_tag)" = "win" ]; }

# Convert a POSIX path (e.g., /c/Users/...) to a Windows-native path
# (e.g., C:/Users/...) using cygpath. Only needed on Windows/MSYS2/Cygwin.
# QEMU on Windows requires native paths for -drive, -cdrom, -kernel, -initrd.
qemu_native_path() {
    local path="$1"
    if is_windows && command -v cygpath >/dev/null 2>&1; then
        cygpath -m "$path"
    else
        echo "$path"
    fi
}

# Validate that a command exists on PATH, with an optional human-readable label.
require_command() {
    local cmd="$1" label="${2:-$1}"
    command -v "$cmd" >/dev/null 2>&1 || {
        echo "Error: ${label} ('${cmd}') is not installed or not on PATH." >&2
        return 1
    }
}

# Locate qemu-system-x86_64 binary. On Windows, also checks common install paths
# (Program Files, LOCALAPPDATA) since QEMU may not be on PATH by default.
resolve_qemu() {
    local binary="qemu-system-x86_64"
    if command -v "$binary" >/dev/null 2>&1; then
        command -v "$binary"
        return 0
    fi
    local candidate
    local candidates=(
        "/c/Program Files/qemu/${binary}.exe"
        "/c/Program Files (x86)/qemu/${binary}.exe"
        "${LOCALAPPDATA:-}/Programs/qemu/${binary}.exe"
    )
    for candidate in "${candidates[@]}"; do
        if [ -n "$candidate" ] && [ -x "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done
    echo "Error: QEMU ('${binary}') is not installed or not on PATH." >&2
    return 1
}

# Locate qemu-img binary. First checks for it as a sibling of qemu-system-x86_64,
# then falls back to PATH. Handles .exe suffix on Windows.
resolve_qemu_img() {
    local qemu_bin="${1:-$(resolve_qemu)}"
    local sibling="$(dirname "$qemu_bin")/qemu-img"
    [ -x "${sibling}.exe" ] && sibling="${sibling}.exe"
    if [ -x "$sibling" ]; then
        echo "$sibling"
    elif command -v qemu-img >/dev/null 2>&1; then
        command -v qemu-img
    else
        echo "Error: qemu-img is not installed or not on PATH." >&2
        return 1
    fi
}

# On Windows/MSYS2, add common paths that contain SSH, ssh-keygen, cygpath, etc.
# These are not always on PATH in a bare MSYS2 environment. The QEMU_ALPINE_SKIP_MSYS2_PATH
# flag disables this if the user has already configured their own PATH.
ensure_msys2_tools() {
    [ "${QEMU_ALPINE_SKIP_MSYS2_PATH:-0}" = "1" ] && return 0
    if is_windows; then
        local current_user dir
        current_user="$(id -un)"
        local candidates=(
            "/c/Users/${current_user}/msys2/ucrt64/bin"
            "/c/msys64/ucrt64/bin"
            "/c/Users/${current_user}/msys2/usr/bin"
            "/c/msys64/usr/bin"
            "/c/Windows/System32/OpenSSH"
        )
        for dir in "${candidates[@]}"; do
            if [ -d "$dir" ] && [[ ":$PATH:" != *":$dir:"* ]]; then
                export PATH="$dir:$PATH"
            fi
        done
    fi
}

ensure_msys2_tools

# Load a key=value profile file (like a simplified .env file).
# Security: rejects shell expansion ($(), ${}, backticks) to prevent injection.
# Handles Windows CRLF line endings by stripping \r.
# Only accepts lines matching KEY=VALUE format; skips comments and blank lines.
load_profile() {
    local profile_path="${1:-}"
    if [ -z "$profile_path" ] || [ ! -f "$profile_path" ]; then
        echo "Error: Profile not found: ${profile_path:-<empty>}." >&2
        return 1
    fi
    local line
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line%$'\r'}"
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "${line//[[:space:]]/}" ]] && continue
        if [[ "$line" =~ \$[\(\{] ]] || [[ "$line" =~ \` ]]; then
            echo "Error: Profile contains shell expansion: ${line}" >&2
            return 1
        fi
        if [[ ! "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
            echo "Error: Invalid profile entry: ${line}" >&2
            return 1
        fi
        export "$line"
    done < "$profile_path"
}

require_profile_value() {
    local key="$1"
    [ -n "${!key:-}" ] || {
        echo "Error: Required profile key '${key}' is not set." >&2
        return 1
    }
}

# Validate that a value is a valid TCP port number (1–65535).
validate_port() {
    local port="$1" label="${2:-port}"
    if [[ ! "$port" =~ ^[0-9]+$ ]] || [ "$port" -lt 1 ] || [ "$port" -gt 65535 ]; then
        echo "Error: ${label} must be an integer from 1 to 65535 (got '${port}')." >&2
        return 1
    fi
}

# Validate a port range for Testcontainers: start ≤ end, at most 512 ports.
validate_port_range() {
    local start="$1" end="$2"
    validate_port "$start" "TESTCONTAINERS_PORT_START"
    validate_port "$end" "TESTCONTAINERS_PORT_END"
    [ "$start" -le "$end" ] || {
        echo "Error: Testcontainers port range start must not exceed end." >&2
        return 1
    }
    [ $((end - start + 1)) -le 512 ] || {
        echo "Error: Testcontainers port range may contain at most 512 ports." >&2
        return 1
    }
}

# Check if the QEMU binary supports a given accelerator (whpx, kvm, etc.)
# by querying `qemu -accel help`.
qemu_supports_accelerator() {
    local qemu_bin="$1" accelerator="$2"
    "$qemu_bin" -accel help 2>/dev/null | grep -qx "$accelerator"
}

# Probe WHPX availability by launching a minimal QEMU instance with -accel whpx.
# The instance is started with -S (stopped) to avoid actual execution; we check
# if it survives for 1 second, then kill it. This verifies the Windows hypervisor
# is active and QEMU can use it without needing a full VM boot.
probe_whpx() {
    local qemu_bin="$1" probe_pid
    "$qemu_bin" \
        -name qemu-alpine-docker-whpx-probe \
        -accel whpx \
        -cpu qemu64 \
        -machine q35 \
        -m 64 \
        -smp 1 \
        -nodefaults \
        -display none \
        -S >/dev/null 2>&1 &
    probe_pid=$!
    sleep 1
    if ! process_is_running "$probe_pid"; then
        wait "$probe_pid" 2>/dev/null || true
        return 1
    fi
    kill "$probe_pid" 2>/dev/null || true
    wait_for_process_exit "$probe_pid" 5 || kill -9 "$probe_pid" 2>/dev/null || true
}

# Configure QEMU acceleration. Supports three modes:
#   auto  — on Windows, try WHPX first; fall back to TCG (software emulation)
#   whpx  — force WHPX (Windows Hypervisor Platform); fails if unavailable
#   tcg   — force TCG (software emulation); works everywhere but is slower
#
# Sets two global variables used by all QEMU launch commands:
#   QEMU_ACCELERATOR — "whpx" or "tcg"
#   QEMU_ACCEL_ARGS  — array of -accel and -cpu arguments
configure_qemu_acceleration() {
    local qemu_bin="$1" requested="${VM_ACCELERATOR:-auto}"
    case "$requested" in
        auto)
            if is_windows && qemu_supports_accelerator "$qemu_bin" whpx && probe_whpx "$qemu_bin"; then
                QEMU_ACCELERATOR="whpx"
                QEMU_ACCEL_ARGS=(-accel whpx -cpu qemu64)
            else
                QEMU_ACCELERATOR="tcg"
                QEMU_ACCEL_ARGS=(-accel tcg,thread=multi -cpu max)
            fi
            ;;
        whpx)
            is_windows || {
                echo "Error: WHPX acceleration is only supported on Windows." >&2
                return 1
            }
            qemu_supports_accelerator "$qemu_bin" whpx && probe_whpx "$qemu_bin" || {
                echo "Error: WHPX is unavailable. Enable the Windows hypervisor or set VM_ACCELERATOR=tcg." >&2
                return 1
            }
            QEMU_ACCELERATOR="whpx"
            QEMU_ACCEL_ARGS=(-accel whpx -cpu qemu64)
            ;;
        tcg)
            QEMU_ACCELERATOR="tcg"
            QEMU_ACCEL_ARGS=(-accel tcg,thread=multi -cpu max)
            ;;
        *)
            echo "Error: VM_ACCELERATOR must be auto, whpx, or tcg (got '${requested}')." >&2
            return 1
            ;;
    esac
}

# Render a template file by replacing {{PLACEHOLDER}} markers with values.
# Runs in a subshell to isolate variable modifications.
# Security: each placeholder must be a NAME/value pair; the function rejects
# any unresolved {{UPPERCASE_PLACEHOLDER}} after all replacements are done.
# Uses atomic write (temp file + mv) to avoid partial writes.
render_template() (
    local template_path="$1" output_path="$2"
    shift 2
    [ -f "$template_path" ] || {
        echo "Error: Template not found: ${template_path}." >&2
        return 1
    }
    [ $(( $# % 2 )) -eq 0 ] || {
        echo "Error: Template replacements must be NAME/value pairs." >&2
        return 1
    }

    local content placeholder value output_dir temp_path
    content="$(<"$template_path")"
    shopt -u patsub_replacement 2>/dev/null || true
    while [ "$#" -gt 0 ]; do
        placeholder="{{${1}}}"
        value="$2"
        [[ "$content" == *"$placeholder"* ]] || {
            echo "Error: Placeholder ${placeholder} is missing from ${template_path}." >&2
            return 1
        }
        content="${content//"$placeholder"/"$value"}"
        shift 2
    done
    if [[ "$content" =~ \{\{[A-Z][A-Z0-9_]*\}\} ]]; then
        echo "Error: Unresolved placeholder ${BASH_REMATCH[0]} in ${template_path}." >&2
        return 1
    fi

    output_dir="$(dirname "$output_path")"
    mkdir -p "$output_dir"
    temp_path="${output_path}.tmp.${BASHPID:-$$}"
    printf '%s\n' "$content" > "$temp_path"
    mv "$temp_path" "$output_path"
)

# Validate that a container image reference contains only safe characters
# (alphanumeric, dots, slashes, colons, dashes, underscores, @).
# Rejects shell metacharacters like $, ;, etc.
validate_image_reference() {
    local image="$1"
    [[ "$image" =~ ^[A-Za-z0-9._/:@-]+$ ]] || {
        echo "Error: Invalid container image reference '${image}'." >&2
        return 1
    }
}

# Generate an Ed25519 SSH key pair if it doesn't already exist.
# This key is used by all scripts to connect to the guest VM.
ensure_ssh_key() {
    if [ -f "$SSH_KEY" ] && [ -f "${SSH_KEY}.pub" ]; then return 0; fi
    mkdir -p "$(dirname "$SSH_KEY")"
    ssh-keygen -t ed25519 -f "$SSH_KEY" -N "" -q
    echo "Generated SSH key: ${SSH_KEY}" >&2
}

# Returns the SSH port from the profile or default (2222).
ssh_port() { echo "${SSH_PORT:-2222}"; }

# Execute a command on the guest via SSH.
# Uses StrictHostKeyChecking=no and BatchMode=yes for non-interactive operation.
# Connects to root@127.0.0.1 on the configured SSH port with the plugin's key.
ssh_exec() {
    ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o ConnectTimeout=10 -o BatchMode=yes -p "$(ssh_port)" -i "$SSH_KEY" \
        "root@${SSH_HOST:-127.0.0.1}" "$@"
}

# Poll until the guest SSH server becomes reachable.
# Optionally checks if a QEMU process is still running (avoids waiting for a dead VM).
# Default timeout is 180 seconds; polls every 2 seconds.
wait_for_ssh() {
    local timeout="${1:-180}" watched_pid="${2:-}" elapsed=0 interval=2
    echo "Waiting for SSH on 127.0.0.1:$(ssh_port) (timeout: ${timeout}s)..." >&2
    while [ "$elapsed" -lt "$timeout" ]; do
        if [ -n "$watched_pid" ] && ! process_is_running "$watched_pid"; then
            echo "Error: QEMU exited before SSH became ready." >&2
            return 1
        fi
        if ssh_exec "echo ready" >/dev/null 2>&1; then
            echo "SSH is ready." >&2
            return 0
        fi
        sleep "$interval"
        elapsed=$((elapsed + interval))
    done
    echo "Error: SSH did not become ready within ${timeout}s." >&2
    return 1
}

# Poll until the Docker API on the guest becomes reachable.
# Uses curl to check the /version endpoint on the host-forwarded Docker port.
# Default timeout is 120 seconds; polls every 2 seconds.
wait_for_docker_api() {
    local timeout="${1:-120}" port="${DOCKER_DAEMON_PORT:-2375}" elapsed=0
    while [ "$elapsed" -lt "$timeout" ]; do
        curl -sf "http://127.0.0.1:${port}/version" >/dev/null 2>&1 && return 0
        sleep 2
        elapsed=$((elapsed + 2))
    done
    echo "Error: Docker API did not become ready on 127.0.0.1:${port}." >&2
    return 1
}

# Download a file from a URL with retries. Tries curl first, falls back to wget.
download_file() {
    local url="$1" dest="$2"
    mkdir -p "$(dirname "$dest")"
    if command -v curl >/dev/null 2>&1; then
        curl -fSL --retry 3 --retry-delay 5 -o "$dest" "$url"
    elif command -v wget >/dev/null 2>&1; then
        wget -q --tries=3 -O "$dest" "$url"
    else
        echo "Error: Neither curl nor wget is available." >&2
        return 1
    fi
}

# Default Alpine ISO URL and filename. Override via environment variables
# for custom mirrors or Alpine versions.
ALPINE_IMAGE_URL="${ALPINE_IMAGE_URL:-https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/x86_64/alpine-virt-3.24.1-x86_64.iso}"
ALPINE_IMAGE_NAME="${ALPINE_IMAGE_NAME:-alpine-virt-3.24.1-x86_64.iso}"

# Download the Alpine ISO if not present, verify its SHA256 checksum, and return its path.
ensure_alpine_image() {
    local image_path="${IMAGES_DIR}/${ALPINE_IMAGE_NAME}"
    local checksum_path="${image_path}.sha256"
    [ -f "$image_path" ] || download_file "$ALPINE_IMAGE_URL" "$image_path"
    [ -f "$checksum_path" ] || download_file "${ALPINE_IMAGE_URL}.sha256" "$checksum_path"
    require_command sha256sum
    (cd "$IMAGES_DIR" && sha256sum -c "$(basename "$checksum_path")") >&2
    echo "$image_path"
}

# --- VM state query helpers ---
# These functions read/write per-VM PID files and the global lock directory.
# The PID file tracks the running QEMU process for a given VM.
# The ready file is created after successful provisioning and verification.
vm_pid_file() { echo "${VM_DIR}/${VM_NAME:-alpine-dev}.pid"; }
vm_ready_file() { echo "${VM_DIR}/${VM_NAME:-alpine-dev}/ready"; }
process_is_running() { local pid="${1:-}"; [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; }
vm_pid() { [ -f "$(vm_pid_file)" ] && cat "$(vm_pid_file)"; }
vm_is_running() { local pid; pid="$(vm_pid 2>/dev/null || true)"; process_is_running "$pid"; }
# Read the QEMU PID from the global active VM lock.
active_vm_pid() { [ -f "${ACTIVE_LOCK_DIR}/qemu.pid" ] && cat "${ACTIVE_LOCK_DIR}/qemu.pid"; }

# --- VM state guard (mutex) ---
# This function implements a simple mutex using a directory as a lock.
# It creates a directory (STATE_GUARD_DIR) and only proceeds if the mkdir succeeds.
# The lock is held for the duration of the callback function.
# This prevents concurrent scripts from corrupting the active VM lock.
# Key design decisions:
#   - Uses a subshell to isolate trap handlers and cleanup
#   - Tracks the owner PID to detect stale locks
#   - Handles SIGINT/SIGTERM by deferring them until cleanup
#   - Retries up to 100 times with 50ms sleep between attempts
with_vm_state_guard() {
    local callback="$1"
    local state_guard_caller_pid="${BASHPID:-$$}"
    shift
    mkdir -p "$RUN_DIR"
    (
        local attempts=0 owner_pid pending_signal="" guard_owned=false
        cleanup_vm_state_guard() {
            if [ "$guard_owned" = "true" ]; then
                rm -f "${STATE_GUARD_DIR}/owner.pid"
                rmdir "$STATE_GUARD_DIR" 2>/dev/null || true
            fi
        }
        trap cleanup_vm_state_guard EXIT
        trap 'pending_signal=130' INT
        trap 'pending_signal=143' TERM
        while ! mkdir "$STATE_GUARD_DIR" 2>/dev/null; do
            [ -z "$pending_signal" ] || exit "$pending_signal"
            owner_pid="$(cat "${STATE_GUARD_DIR}/owner.pid" 2>/dev/null || true)"
            if [ -n "$owner_pid" ] && ! process_is_running "$owner_pid"; then
                echo "Error: stale VM state guard at ${STATE_GUARD_DIR}; remove it after confirming no plugin script is running." >&2
                return 1
            fi
            attempts=$((attempts + 1))
            if [ "$attempts" -ge 100 ]; then
                echo "Error: timed out waiting for the VM state guard at ${STATE_GUARD_DIR}." >&2
                return 1
            fi
            sleep 0.05
        done
        guard_owned=true
        trap 'exit 130' INT
        trap 'exit 143' TERM
        [ -z "$pending_signal" ] || exit "$pending_signal"
        echo "${BASHPID:-$$}" > "${STATE_GUARD_DIR}/owner.pid" || return 1
        "$callback" "$@"
    )
}

# Acquire the global singleton VM lock. This ensures only one VM runs at a time.
# Uses directory-based locking (mkdir is atomic) for reliability across platforms.
# Strategy:
#   1. Try to create the lock directory
#   2. If it exists, check if the owner process is still alive
#   3. If the owner is dead, clean up and re-acquire
#   4. Store VM name, launcher PID, and QEMU PID in the lock directory
acquire_single_vm_lock_guarded() {
    if mkdir "$ACTIVE_LOCK_DIR" 2>/dev/null; then
        echo "${VM_NAME:-unknown}" > "${ACTIVE_LOCK_DIR}/vm-name"
        echo "$state_guard_caller_pid" > "${ACTIVE_LOCK_DIR}/launcher.pid"
        return 0
    fi
    local active_pid active_launcher active_name
    active_pid="$(active_vm_pid 2>/dev/null || true)"
    active_launcher="$(cat "${ACTIVE_LOCK_DIR}/launcher.pid" 2>/dev/null || true)"
    active_name="$(cat "${ACTIVE_LOCK_DIR}/vm-name" 2>/dev/null || echo unknown)"
    local owner_pid=""
    if process_is_running "$active_pid"; then
        owner_pid="$active_pid"
    elif process_is_running "$active_launcher"; then
        owner_pid="$active_launcher"
    fi
    if [ -n "$owner_pid" ]; then
        echo "Error: VM '${active_name}' already owns the global lock (PID ${owner_pid})." >&2
        return 1
    fi
    rm -f "${ACTIVE_LOCK_DIR}/qemu.pid" "${ACTIVE_LOCK_DIR}/launcher.pid" "${ACTIVE_LOCK_DIR}/vm-name"
    if ! rmdir "$ACTIVE_LOCK_DIR" 2>/dev/null || ! mkdir "$ACTIVE_LOCK_DIR" 2>/dev/null; then
        echo "Error: failed to replace stale VM lock at ${ACTIVE_LOCK_DIR}." >&2
        return 1
    fi
    echo "${VM_NAME:-unknown}" > "${ACTIVE_LOCK_DIR}/vm-name"
    echo "$state_guard_caller_pid" > "${ACTIVE_LOCK_DIR}/launcher.pid"
}

acquire_single_vm_lock() { with_vm_state_guard acquire_single_vm_lock_guarded; }

# Record the QEMU process PID in both the per-VM PID file and the global lock.
# This allows other scripts to verify the VM is running and to stop it.
register_vm_process() {
    local pid="$1"
    echo "$pid" > "$(vm_pid_file)"
    echo "$pid" > "${ACTIVE_LOCK_DIR}/qemu.pid"
}

# Release the global singleton VM lock by removing all files and the lock directory.
# Called by start-vm.sh after the VM is running and by stop-vm.sh after shutdown.
release_single_vm_lock_guarded() {
    rm -f "${ACTIVE_LOCK_DIR}/qemu.pid" "${ACTIVE_LOCK_DIR}/launcher.pid" "${ACTIVE_LOCK_DIR}/vm-name"
    rmdir "$ACTIVE_LOCK_DIR" 2>/dev/null || true
}

release_single_vm_lock() { with_vm_state_guard release_single_vm_lock_guarded; }

# Clean up VM process state: remove PID file and conditionally release the global lock.
# The lock is only released if the current VM name matches the lock's VM name AND
# the QEMU process and launcher process are both dead. This prevents accidentally
# releasing the lock for a different VM that might still be running.
clear_vm_process_state_guarded() {
    rm -f "$(vm_pid_file)"
    local active_name active_pid active_launcher current_launcher
    active_name="$(cat "${ACTIVE_LOCK_DIR}/vm-name" 2>/dev/null || true)"
    active_pid="$(active_vm_pid 2>/dev/null || true)"
    active_launcher="$(cat "${ACTIVE_LOCK_DIR}/launcher.pid" 2>/dev/null || true)"
    current_launcher="$state_guard_caller_pid"
    if [ "$active_name" = "${VM_NAME:-}" ] && \
       ! process_is_running "$active_pid" && \
       { [ "$active_launcher" = "$current_launcher" ] || ! process_is_running "$active_launcher"; }; then
        rm -f "${ACTIVE_LOCK_DIR}/qemu.pid" "${ACTIVE_LOCK_DIR}/launcher.pid" "${ACTIVE_LOCK_DIR}/vm-name"
        rmdir "$ACTIVE_LOCK_DIR" 2>/dev/null || true
    fi
}

clear_vm_process_state() { with_vm_state_guard clear_vm_process_state_guarded; }

# Wait for a process to exit, with a timeout. Returns 0 if the process exited,
# non-zero if it's still running after the timeout.
wait_for_process_exit() {
    local pid="$1" timeout="$2" elapsed=0
    while process_is_running "$pid" && [ "$elapsed" -lt "$timeout" ]; do
        sleep 1
        elapsed=$((elapsed + 1))
    done
    ! process_is_running "$pid"
}

# Build the QEMU -netdev argument for user-mode networking with port forwarding.
#
# This is the core networking configuration. It creates a QEMU user-mode network
# backend with the following port mappings:
#   - SSH:       host:SSH_PORT → guest:22
#   - Docker API: host:DOCKER_DAEMON_PORT → guest:2375
#   - Testcontainers port range: host:TESTCONTAINERS_PORT_START-END → guest:same ports
#   - Custom PORT_FORWARD mappings: host:port → guest:port
#
# All ports are bound to 127.0.0.1 (localhost only) for security.
# Validation ensures no port collisions between the above categories.
# The Testcontainers port range allows up to 512 ports for container publishing.
build_netdev_value() {
    local ssh_value="${SSH_PORT:-2222}" docker_value="${DOCKER_DAEMON_PORT:-2375}"
    local range_start="${TESTCONTAINERS_PORT_START:-20000}" range_end="${TESTCONTAINERS_PORT_END:-20255}"
    validate_port "$ssh_value" "SSH_PORT"
    validate_port "$docker_value" "DOCKER_DAEMON_PORT"
    validate_port_range "$range_start" "$range_end"
    [ "$ssh_value" != "$docker_value" ] || { echo "Error: SSH and Docker API ports must differ." >&2; return 1; }
    if { [ "$ssh_value" -ge "$range_start" ] && [ "$ssh_value" -le "$range_end" ]; } || \
       { [ "$docker_value" -ge "$range_start" ] && [ "$docker_value" -le "$range_end" ]; }; then
        echo "Error: Fixed SSH/Docker API ports must be outside the Testcontainers range." >&2
        return 1
    fi
    local value="user,id=net0,hostfwd=tcp:127.0.0.1:${ssh_value}-:22,hostfwd=tcp:127.0.0.1:${docker_value}-:2375"
    local port
    for ((port=range_start; port<=range_end; port++)); do
        value+=",hostfwd=tcp:127.0.0.1:${port}-:${port}"
    done
    if [ -n "${PORT_FORWARD:-}" ]; then
        local mapping host_port guest_port
        IFS=',' read -ra mappings <<< "$PORT_FORWARD"
        for mapping in "${mappings[@]}"; do
            [[ "$mapping" =~ ^[0-9]+:[0-9]+$ ]] || { echo "Error: Invalid PORT_FORWARD mapping '${mapping}'." >&2; return 1; }
            host_port="${mapping%%:*}"; guest_port="${mapping##*:}"
            validate_port "$host_port" "PORT_FORWARD host port"
            validate_port "$guest_port" "PORT_FORWARD guest port"
            if [ "$host_port" = "$ssh_value" ] || [ "$host_port" = "$docker_value" ] || \
               { [ "$host_port" -ge "$range_start" ] && [ "$host_port" -le "$range_end" ]; }; then
                echo "Error: PORT_FORWARD host port ${host_port} collides with a reserved port." >&2
                return 1
            fi
            value+=",hostfwd=tcp:127.0.0.1:${host_port}-:${guest_port}"
        done
    fi
    echo "$value"
}
