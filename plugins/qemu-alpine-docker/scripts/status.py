"""Read-only local VM and Docker status. No provisioning or state-file writes."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
from process_identity import windows_pid
import urllib.error
import urllib.request
from status_resources import container_resources, guest_resources, host_resources, unavailable

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT = 2
MAX_RESPONSE = 2 * 1024 * 1024


def read_profile(path):
    values = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", line) or any(x in line for x in ("$(", "${", "`")):
            raise ValueError("Profile contains unsupported shell syntax")
        key, value = line.split("=", 1)
        values[key] = value
    name = values.get("VM_NAME", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
        raise ValueError("Profile VM_NAME must be a simple directory name")
    for key in ("SSH_PORT", "DOCKER_DAEMON_PORT"):
        value = values.get(key, "")
        if not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= 65535:
            raise ValueError(f"Invalid {key} in profile")
        values[key] = int(value)
    return values


def read_pid(path):
    try:
        text = path.read_text(encoding="utf-8").strip()
        return int(text) if re.fullmatch(r"[1-9][0-9]{0,9}", text) else None
    except FileNotFoundError:
        return None


def process_state(pid):
    """Verify executable identity; a reused PID is not a running QEMU VM."""
    if pid is None:
        return "stopped"
    try:
        if os.name == "nt":
            pid = windows_pid(pid)
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                 f"$p = Get-Process -Id {pid} -ErrorAction SilentlyContinue; if ($p) {{$p.ProcessName}}; exit 0"],
                capture_output=True, text=True, timeout=TIMEOUT, check=True,
            )
            name = result.stdout.strip()
        elif Path("/proc").is_dir():
            # comm truncates long names; executable path preserves QEMU's full name.
            proc = Path("/proc") / str(pid)
            stat = (proc / "stat").read_text()
            if stat.rsplit(")", 1)[1].split()[0] == "Z":
                return "stopped"
            name = (proc / "exe").resolve(strict=True).name
        else:
            result = subprocess.run(["ps", "-p", str(pid), "-o", "comm="], capture_output=True,
                                    text=True, timeout=TIMEOUT, check=False)
            name = Path(result.stdout.strip()).name if result.stdout.strip() else ""
        return "running" if name.lower() in ("qemu-system-x86_64", "qemu-system-x86_64.exe") else "stopped"
    except FileNotFoundError:
        return "unknown" if os.name == "nt" else "stopped"
    except (OSError, subprocess.SubprocessError, IndexError):
        return "unknown"


def process_accelerator(pid):
    """Expose only the selected accelerator, never the process command line."""
    try:
        if os.name == "nt":
            pid = windows_pid(pid)
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                 f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}').CommandLine"],
                capture_output=True, text=True, timeout=TIMEOUT, check=True,
            )
            match = re.search(r'(?:^|\s)-accel\s+"?([a-z]+)', result.stdout)
            value = match.group(1) if match else None
        elif Path("/proc").is_dir():
            args = (Path("/proc") / str(pid) / "cmdline").read_bytes().decode(errors="replace").split("\0")
            value = args[args.index("-accel") + 1].split(",", 1)[0] if "-accel" in args else None
        else:
            return None
        return value if value in ("kvm", "whpx", "tcg", "hvf") else None
    except (OSError, subprocess.SubprocessError, IndexError):
        return None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Docker API redirects are not followed")


def docker_get(port, endpoint):
    # Never inherit network proxy variables for this privileged loopback API.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    # Non-streaming stats wait for two Docker samples and can take nearly two seconds.
    timeout = 4 if endpoint.endswith("/stats?stream=false") else TIMEOUT
    with opener.open(f"http://127.0.0.1:{port}{endpoint}", timeout=timeout) as response:
        data = response.read(MAX_RESPONSE + 1)
        if len(data) > MAX_RESPONSE:
            raise ValueError("Docker API response exceeds 2 MiB")
        if endpoint == "/_ping":
            if data.strip() != b"OK":
                raise ValueError("Docker API returned an unexpected ping response")
            return True
        return json.loads(data)


def failure_message(error):
    if isinstance(error, urllib.error.URLError):
        error = error.reason
    if isinstance(error, (TimeoutError, socket.timeout)):
        return "Probe timed out"
    if isinstance(error, urllib.error.HTTPError):
        return f"Docker API returned HTTP {error.code}"
    if isinstance(error, (ValueError, TypeError, KeyError)):
        return "Invalid or unsupported Docker API response"
    return "Local service is unreachable"


def ssh_health(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=TIMEOUT) as connection:
            connection.settimeout(TIMEOUT)
            banner = connection.recv(256)
            if not banner.startswith(b"SSH-"):
                return {"state": "unhealthy", "detail": "Port responds without an SSH banner"}
        return {"state": "healthy", "detail": "SSH banner received; authentication was not tested"}
    except OSError as error:
        return {"state": "unreachable", "detail": failure_message(error)}


def docker_health(port):
    try:
        docker_get(port, "/_ping")
    except (OSError, ValueError) as error:
        state = "unhealthy" if isinstance(error, (urllib.error.HTTPError, ValueError)) else "unreachable"
        return {"state": state, "detail": failure_message(error)}, {"state": "unavailable", "items": []}
    health = {"state": "healthy", "detail": "Docker API ping succeeded"}
    try:
        version = docker_get(port, "/version")
        health["version"] = str(version["Version"])[:80]
    except (OSError, ValueError, TypeError, KeyError) as error:
        health["detail"] += "; version unavailable"
    try:
        containers = docker_get(port, "/containers/json?all=1")
        if not isinstance(containers, list):
            raise ValueError("Expected container list")
        items = []
        stats_targets = []
        for container in containers:
            if not isinstance(container, dict):
                raise ValueError("Expected container object")
            names = container.get("Names") or []
            ports = container.get("Ports") or []
            item = {
                "id": str(container.get("Id", ""))[:12],
                "name": str(names[0]).lstrip("/")[:200] if names else "Unnamed",
                "image": str(container.get("Image", ""))[:300],
                "state": str(container.get("State", "unknown"))[:80],
                "status": str(container.get("Status", ""))[:300],
                "ports": [f"{p.get('IP') or '*'}:{p['PublicPort']} → {p['PrivatePort']}/{p.get('Type', 'tcp')}"
                          for p in ports if isinstance(p, dict) and "PublicPort" in p and "PrivatePort" in p][:32],
                "resources": unavailable("Container is not running", "not-running"),
            }
            items.append(item)
            if item["state"] == "running":
                identifier = container.get("Id", "")
                item["resources"] = unavailable("Resource sampling limit reached (32 running containers)")
                if not isinstance(identifier, str) or not re.fullmatch(r"[a-fA-F0-9]{12,64}", identifier):
                    item["resources"] = unavailable("Container identifier is invalid")
                elif len(stats_targets) < 32:
                    stats_targets.append((item, identifier))
        with ThreadPoolExecutor(max_workers=8) as pool:
            samples = [(item, pool.submit(container_resources, port, identifier, docker_get))
                       for item, identifier in stats_targets]
            for item, sample in samples:
                item["resources"] = sample.result()
        items.sort(key=lambda item: (item["state"] != "running", item["name"]))
        return health, {"state": "available", "items": items}
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        return health, {"state": "unavailable", "items": [], "detail": failure_message(error)}


def native_path(value):
    if os.name == "nt" and str(value).startswith("/"):
        return subprocess.run(["cygpath", "-w", str(value)], capture_output=True, text=True,
                              timeout=TIMEOUT, check=True).stdout.strip()
    return value


def collect_status():
    profile = read_profile(native_path(os.environ.get("QEMU_STATUS_PROFILE") or ROOT / "profiles/dev.profile"))
    # Native Python on Windows resolves USERPROFILE; Git Bash/MSYS paths may be used via cygpath.
    raw_base = os.environ.get("QEMU_ALPINE_BASE_DIR")
    if raw_base:
        raw_base = native_path(raw_base)
    base = Path(raw_base).expanduser() if raw_base else Path.home() / ".qemu-alpine-docker"
    name = profile["VM_NAME"]
    home = base / "vms" / name
    pid = read_pid(base / "vms" / f"{name}.pid")
    state = process_state(pid)
    warnings = []
    if state == "unknown":
        warnings.append("QEMU process identity could not be verified")
    if pid and state == "stopped":
        warnings.append("PID file is stale or belongs to a different executable")
    try:
        active = (base / "run/active-vm.lock/vm-name").read_text().strip()
        if active != name:
            warnings.append("Another VM owns the global lock; select its profile with QEMU_STATUS_PROFILE")
    except FileNotFoundError:
        pass
    with ThreadPoolExecutor(max_workers=4) as pool:
        ssh = pool.submit(ssh_health, profile["SSH_PORT"])
        docker = pool.submit(docker_health, profile["DOCKER_DAEMON_PORT"])
        resources = pool.submit(host_resources, windows_pid(pid) if os.name == "nt" and state == "running" else pid if state == "running" else None)
        guest = pool.submit(guest_resources, base, profile["SSH_PORT"], state == "running")
        docker_status, containers = docker.result()
        ssh_status = ssh.result()
        resource_status = {**resources.result(), "guest": guest.result()}
    if state != "running" and (ssh_status["state"] == "healthy" or docker_status["state"] == "healthy"):
        warnings.append("Local services respond, but this profile's QEMU process is not verified")
    return {
        "observedAt": datetime.now(timezone.utc).isoformat(),
        "vm": {"name": name, "state": state, "pid": pid, "diskPresent": (home / "disk.qcow2").is_file(),
               "provisioned": (home / "ready").is_file(), "memoryMiB": profile.get("VM_MEMORY"),
               "cpus": profile.get("VM_CPUS"), "acceleratorPolicy": profile.get("VM_ACCELERATOR", "auto"),
               "accelerator": process_accelerator(pid) if state == "running" else None},
        "services": {"ssh": {**ssh_status, "port": profile["SSH_PORT"]},
                     "docker": {**docker_status, "port": profile["DOCKER_DAEMON_PORT"]}},
        "containers": containers,
        "resources": resource_status,
        "warnings": warnings,
    }


if __name__ == "__main__":
    print(json.dumps(collect_status(), indent=2))
