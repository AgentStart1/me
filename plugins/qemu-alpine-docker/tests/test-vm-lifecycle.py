"""Exercise lifecycle races with real QEMU/gvproxy, mocked guest IO and no disks."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from process_identity import identity


def available_ports():
    ports = []
    for _ in range(4):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            ports.append(probe.getsockname()[1])
    for start in range(26000, 29000, 3):
        sockets = []
        try:
            for port in range(start, start + 3):
                sock = socket.socket()
                sockets.append(sock)
                sock.bind(("127.0.0.1", port))
            return ports, start
        except OSError:
            pass
        finally:
            for sock in sockets:
                sock.close()
    raise RuntimeError("No isolated three-port fixture range")


def wait_for(predicate, process=None, timeout=30):
    deadline = time.monotonic() + timeout
    while not predicate():
        if process and process.poll() is not None:
            raise AssertionError("Fixture command exited before barrier; inspect its log")
        assert time.monotonic() < deadline, "Fixture barrier timeout"
        time.sleep(0.05)


def main():
    bash = os.environ.get("BASH_TEST_BINARY") or shutil.which("bash")
    qemu = os.environ.get("QEMU_TEST_BINARY") or shutil.which("qemu-system-x86_64")
    if os.name == "nt":
        candidate = Path(bash).parent.parent / "usr/bin/bash.exe"
        if candidate.exists():
            bash = str(candidate)
    assert bash and qemu, "Real Bash and QEMU are required"
    helper = str(Path(os.environ["GVPROXY_BINARY"]).resolve())
    with tempfile.TemporaryDirectory() as directory:
        fixture = Path(directory)
        plugin = fixture / "plugin"
        shutil.copytree(ROOT / "scripts", plugin / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "templates", plugin / "templates")
        for file in plugin.rglob("*.sh"):
            file.write_bytes(file.read_bytes().replace(b"\r\n", b"\n"))
        bin_dir = fixture / "bin"
        bin_dir.mkdir()
        (bin_dir / "qemu-system-x86_64").write_text('''#!/bin/bash
name=
while [ $# -gt 0 ]; do
    case "$1" in -name) name="$2"; shift;; esac
    shift
done
exec "$QEMU_TEST_BINARY" -name "$name" -accel tcg -m 64 -smp 1 -nodefaults -display none -S
''')
        (bin_dir / "ssh").write_text('''#!/bin/bash
if [[ "$*" == *"echo ready"* ]]; then [ -f "$FIXTURE_READY" ]; exit; fi
if [[ "$*" == *poweroff* ]]; then
    "$FIXTURE_PYTHON" "$FIXTURE_PLUGIN/scripts/qemu-control.py" stop \
        --pid "$(cat "$QEMU_ALPINE_BASE_DIR/vms/lifecycle-fixture.pid")" --name lifecycle-fixture \
        --state "$QEMU_ALPINE_BASE_DIR/vms/lifecycle-fixture.qemu.json"
fi
if [[ "$*" == *"sh -s"* ]]; then cat >/dev/null; fi
exit 0
''')
        (bin_dir / "curl").write_text('''#!/bin/bash
if [[ "$*" == *services/forwarder* ]]; then exec "$FIXTURE_CURL" "$@"; fi
printf '{}'
''')
        for file in bin_dir.iterdir():
            file.chmod(0o755)
        ports, start = available_ports()
        profile = fixture / "fixture.profile"
        profile.write_text(f"VM_NAME=lifecycle-fixture\nVM_ACCELERATOR=tcg\nVM_MEMORY=64\nVM_CPUS=1\nVM_DISK_SIZE=1G\n"
                           f"SSH_PORT={ports[0]}\nDOCKER_DAEMON_PORT={ports[1]}\n"
                           f"GVPROXY_QEMU_PORT={ports[2]}\nGVPROXY_API_PORT={ports[3]}\n"
                           f"TESTCONTAINERS_PORT_START={start}\nTESTCONTAINERS_PORT_END={start+2}\n"
                           "TESTCONTAINERS_RESOURCE_METRICS=false\n")
        base = fixture / "state"
        home = base / "vms/lifecycle-fixture"
        home.mkdir(parents=True)
        disk = home / "disk.qcow2"
        disk.write_bytes(b"untouched fixture disk")
        (home / "ready").touch()
        ready = fixture / "guest-ready"
        env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ["PATH"],
                   QEMU_TEST_BINARY=str(Path(qemu).resolve()), GVPROXY_BINARY=helper,
                   QEMU_ALPINE_BASE_DIR=str(base), QEMU_ALPINE_SKIP_MSYS2_PATH="1",
                   FIXTURE_READY=str(ready), FIXTURE_PYTHON=sys.executable,
                   FIXTURE_PLUGIN=str(plugin), FIXTURE_CURL=shutil.which("curl"), BOOT_TIMEOUT="30")
        env.pop("VM_OPERATION_TOKEN", None)
        logs = []
        children = []
        def launch(script, **overrides):
            log = open(fixture / f"{len(logs)}-{script}.log", "wb")
            logs.append(log)
            child = subprocess.Popen([bash, (plugin / "scripts" / (script + ".sh")).as_posix(), profile.as_posix()], env=dict(env, **overrides),
                                     stdout=log, stderr=log)
            children.append(child)
            return child
        operation = base / "run/vm-operation.lock"
        qstate = base / "vms/lifecycle-fixture.qemu.json"
        hstate = base / "vms/lifecycle-fixture.gvproxy.pid"
        try:
            owner = launch("start-vm")
            wait_for(qstate.exists, owner)
            qrecord, hrecord = json.loads(qstate.read_text()), json.loads(hstate.read_text())
            for contender in ["start-vm", "stop-vm", "create-vm", "migrate-vm-network"]:
                assert launch(contender).wait(timeout=15) != 0, contender
                assert identity(qrecord["pid"]) == qrecord["identity"]
                assert json.loads(qstate.read_text()) == qrecord
            ready.touch()
            assert owner.wait(timeout=30) == 0
            assert not operation.exists()
            assert launch("start-vm").wait(timeout=30) == 0  # Healthy idempotency.
            assert launch("migrate-vm-network").wait(timeout=60) == 0  # Nested stop/start.
            assert not operation.exists()
            assert launch("stop-vm").wait(timeout=30) == 0
            assert not qstate.exists() and not hstate.exists()
            # TERM at readiness must terminate both owned processes and release locks.
            ready.unlink()
            owner = launch("start-vm")
            wait_for(qstate.exists, owner)
            qrecord, hrecord = json.loads(qstate.read_text()), json.loads(hstate.read_text())
            shell_pid = int((operation / "owner.pid").read_text())
            subprocess.run([bash, "-lc", f"kill -TERM {shell_pid}"], check=True)
            assert owner.wait(timeout=30) == 143
            assert identity(qrecord["pid"]) is None and identity(hrecord["pid"]) is None
            assert not operation.exists() and not qstate.exists() and not hstate.exists()
            # Startup timeout follows the same cleanup; no retries of failed protocol IO.
            assert launch("start-vm", BOOT_TIMEOUT="1").wait(timeout=30) != 0
            assert not operation.exists() and not qstate.exists() and not hstate.exists()
            # A test command holds the VM reservation; shutdown cannot race it.
            ready.touch()
            assert launch("start-vm").wait(timeout=30) == 0
            guard_command = f'"{(plugin / "scripts/run-testcontainers.sh").as_posix()}"'
            proxy = fixture / "proxy"
            proxy.mkdir()
            proxy_file = proxy / ("docker.exe" if os.name == "nt" else "docker")
            proxy_file.touch()
            proxy_file.chmod(0o755)
            held = subprocess.Popen([bash, str(plugin / "scripts/run-testcontainers.sh"), "--profile", str(profile),
                                     "--", bash, "-c", '"$1" "$2" && exit 99; sleep 3; exit 23',
                                     "test-command", str(plugin / "scripts/stop-vm.sh"), str(profile)],
                                    env=dict(env, QEMU_DOCKER_PROXY_DIR=str(proxy)), stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
            children.append(held)
            wait_for(operation.exists, held)
            assert launch("stop-vm").wait(timeout=15) != 0
            assert held.wait(timeout=15) == 23
            assert not operation.exists()
            assert subprocess.run([bash, str(plugin / "scripts/run-testcontainers.sh"), "--profile", str(profile),
                                   "--", bash, "-c", "exit 0"],
                                  env=dict(env, QEMU_DOCKER_PROXY_DIR=str(proxy)),
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15).returncode == 0
            assert not operation.exists()
            assert launch("stop-vm").wait(timeout=30) == 0
            assert disk.read_bytes() == b"untouched fixture disk"
        finally:
            ready.touch()
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.wait()
            if qstate.exists() and not operation.exists():
                launch("stop-vm").wait(timeout=30)
            for log in logs:
                log.close()
            if sys.exc_info()[0] is not None:
                for log in fixture.glob("*.log"):
                    print(log.name + ":\n" + log.read_text(errors="replace"), file=sys.stderr)
            if os.environ.get("TEST_ARTIFACT_DIR"):
                output = Path(os.environ["TEST_ARTIFACT_DIR"])
                output.mkdir(parents=True, exist_ok=True)
                for log in fixture.glob("*.log"):
                    shutil.copy2(log, output / log.name)
            # Only process records owned by this isolated fixture are eligible for cleanup.
            from process_identity import terminate
            for state in [qstate, hstate]:
                if state.exists():
                    record = json.loads(state.read_text())
                    if identity(record["pid"]) == record["identity"]:
                        terminate(record)
        print("PASS: competing start/stop/create/migrate, nested migration, healthy idempotency, TERM/timeout cleanup, test reservation and disk preservation")


if __name__ == "__main__":
    main()
