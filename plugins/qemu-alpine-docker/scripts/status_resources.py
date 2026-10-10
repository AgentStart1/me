"""Bounded, read-only resource samples; never reuse test-run metrics reports."""
from pathlib import Path
import math
import subprocess


def unavailable(detail, state="unavailable"):
    return {"state": state, "detail": detail}


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("Invalid resource counter")
    return value


def measurement(cpu, used, total):
    used, total = number(used), number(total)
    if total <= 0 or used > total:
        raise ValueError("Invalid memory counters")
    return {"state": "available", "cpuPercent": round(number(cpu), 1) if cpu is not None else None,
            "memoryBytes": used, "memoryLimitBytes": total, "memoryPercent": round(used / total * 100, 1)}


def host_resources(pid):
    try:
        import psutil
    except ImportError:
        missing = unavailable("Install psutil to collect local system resources")
        return {"host": missing, "qemu": missing}
    process = None
    qemu = unavailable("QEMU process is not verified", "not-running")
    if pid:
        try:
            candidate = psutil.Process(pid)
            if candidate.name().lower() in ("qemu-system-x86_64", "qemu-system-x86_64.exe"):
                process = candidate
                process.cpu_percent()
            else:
                qemu = unavailable("PID no longer belongs to QEMU")
        except psutil.Error:
            qemu = unavailable("QEMU process could not be sampled")
    try:
        cpu = psutil.cpu_percent(interval=0.25)
        memory = psutil.virtual_memory()
        host = measurement(cpu, memory.total - memory.available, memory.total)
        if process:
            try:
                qemu = measurement(process.cpu_percent() / (psutil.cpu_count() or 1),
                                   process.memory_info().rss, memory.total)
            except psutil.Error:
                qemu = unavailable("QEMU process exited or could not be sampled")
        return {"host": host, "qemu": qemu}
    except (psutil.Error, OSError, ValueError):
        return {"host": unavailable("Local system resources could not be sampled"), "qemu": qemu}


def guest_resources(base, port, verified):
    if not verified:
        return unavailable("QEMU process is not verified", "not-running")
    key = base / "id_ed25519"
    if not key.is_file():
        return unavailable("Existing VM SSH key is unavailable")
    try:
        script = (Path(__file__).resolve().parents[1] / "templates/guest-resource-sample.sh").read_text()
        result = subprocess.run(
            ["ssh", "-F", "none", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
             "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
             "-o", "ConnectTimeout=2", "-p", str(port), "-i", str(key), "root@127.0.0.1", "sh -s"],
            # Binary stdin keeps LF on Windows; text mode would send CRLF to guest sh.
            input=script.encode("utf-8"), capture_output=True, timeout=4, check=True)
        if len(result.stdout) > 16384:
            raise ValueError("Oversized resource sample")
        first, second, memory = result.stdout.decode("utf-8").split("\n---\n")
        def cpu_counts(line):
            fields = line.split()
            if fields[0] != "cpu" or len(fields) < 6:
                raise ValueError("Invalid CPU sample")
            values = [number(int(value)) for value in fields[1:9]]
            return sum(values), values[3] + values[4]
        total1, idle1 = cpu_counts(first)
        total2, idle2 = cpu_counts(second)
        delta, idle = total2 - total1, idle2 - idle1
        cpu = (delta - idle) / delta * 100 if delta > 0 and 0 <= idle <= delta else None
        values = {line.split()[0].rstrip(":"): int(line.split()[1]) * 1024
                  for line in memory.splitlines() if line.strip()}
        return measurement(cpu, values["MemTotal"] - values["MemAvailable"], values["MemTotal"])
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError):
        return unavailable("Guest resource sample unavailable; check VM SSH access")


def container_resources(port, identifier, get):
    try:
        data = get(port, f"/containers/{identifier}/stats?stream=false")
        current, previous = data["cpu_stats"], data.get("precpu_stats", {})
        cpu = None
        if previous.get("cpu_usage") and "system_cpu_usage" in previous:
            delta = number(current["cpu_usage"]["total_usage"]) - number(previous["cpu_usage"]["total_usage"])
            system = number(current["system_cpu_usage"]) - number(previous["system_cpu_usage"])
            cores = number(current.get("online_cpus") or len(current["cpu_usage"].get("percpu_usage", [])))
            if system > 0 and delta >= 0 and cores > 0:
                cpu = delta / system * cores * 100
        memory = data["memory_stats"]
        usage = number(memory["usage"])
        stats = memory.get("stats", {})
        cache = number(stats.get("total_inactive_file", stats.get("inactive_file", 0)))
        return measurement(cpu, usage - cache if cache <= usage else usage, memory["limit"])
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
        return unavailable("Container resource sample unavailable")
