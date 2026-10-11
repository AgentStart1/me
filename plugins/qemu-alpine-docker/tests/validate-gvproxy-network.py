# /// script
# requires-python = ">=3.11"
# dependencies = ["psycopg[binary]>=3.2,<4"]
# ///
"""Opt-in application probes against an idle, already-running plugin VM.

Creates only owned temporary fixtures, never retries a failed protocol connection.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import psycopg

API = "http://127.0.0.1:2375"
FORWARDER = "http://127.0.0.1:19201/services/forwarder/"


def request(url, data=None, method=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as response:
        body = response.read()
        return json.loads(body) if body else None


def ssh(command, data=None):
    base = Path(os.environ.get("QEMU_ALPINE_BASE_DIR", Path.home() / ".qemu-alpine-docker"))
    result = subprocess.run(["ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                             "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-p", "2222",
                             "-i", str(base / "id_ed25519"), "root@127.0.0.1", command],
                            check=True, capture_output=True, text=True, timeout=120, input=data)
    return result.stdout


def main():
    assert request(API + "/containers/json") == [], "VM must be idle"
    ports = list(range(21000, 21070))
    exposed = []
    database = None
    result = {}
    try:
        fixture = Path(__file__).parent / "fixtures/gvproxy-http.go"
        ssh("set -eu; mkdir /tmp/me-gvproxy-http; cat > /tmp/me-gvproxy-http/main.go; "
            "go build -o /tmp/me-gvproxy-http/server /tmp/me-gvproxy-http/main.go; "
            "nohup /tmp/me-gvproxy-http/server >/tmp/me-gvproxy-http/server.log 2>&1 </dev/null & "
            "echo $! > /tmp/me-gvproxy-http/pids; "
            "for attempt in $(seq 1 50); do [ ! -f /tmp/me-gvproxy-http/ready ] || exit 0; sleep 0.1; done; exit 1",
            fixture.read_text())
        existing = {rule["local"]: rule for rule in request(FORWARDER + "all")}
        for port in ports:
            if f"127.0.0.1:{port}" in existing:
                assert existing[f"127.0.0.1:{port}"]["remote"] == f"192.168.127.2:{port}"
                continue
            request(FORWARDER + "expose", {"local": f"127.0.0.1:{port}", "remote": f"192.168.127.2:{port}", "protocol": "tcp"})
            exposed.append(port)
        assert len(request(FORWARDER + "all")) >= 91
        count = 0
        for _ in range(3):
            for port in ports:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
                    assert response.read() == b"gvproxy-application-ok"
                count += 1
        result["http"] = {"forwards": 70, "total_rules": len(request(FORWARDER + "all")), "responses": count,
                          "first_middle_last": [ports[0], ports[len(ports)//2], ports[-1]]}
        # Temporary DB has no secrets and exists solely for loopback protocol probes.
        database = request(API + "/containers/create?name=me-gvproxy-postgres", {
            "Image": "postgres:11-alpine", "Env": ["POSTGRES_HOST_AUTH_METHOD=trust"],
            "HostConfig": {"PortBindings": {"5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": "20000"}]}},
            "ExposedPorts": {"5432/tcp": {}}})["Id"]
        request(API + f"/containers/{database}/start", method="POST")
        # The image's temporary init server accepts Unix sockets before restart.
        # Wait for the final server's container-local TCP listener; host load never retries.
        deadline = time.monotonic() + 60
        while ssh("docker exec me-gvproxy-postgres pg_isready -h 127.0.0.1 -q; echo $?").strip() != "0":
            assert time.monotonic() < deadline, "Postgres startup timeout"
            time.sleep(0.2)
        def connect(_):
            with psycopg.connect(host="127.0.0.1", port=20000, user="postgres", dbname="postgres", connect_timeout=5) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1, pg_sleep(0.03)")
                    assert cursor.fetchone()[0] == 1
            return 1
        for concurrency in [8, 16]:
            count = 0
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                for _ in range(40):
                    count += sum(pool.map(connect, range(concurrency)))
            result[f"postgres_concurrency_{concurrency}"] = {"connections": count, "failed": 0}
    finally:
        if database:
            request(API + f"/containers/{database}?force=true&v=true", method="DELETE")
        for port in exposed:
            request(FORWARDER + "unexpose", {"local": f"127.0.0.1:{port}", "remote": f"192.168.127.2:{port}", "protocol": "tcp"})
        ssh("if [ -f /tmp/me-gvproxy-http/pids ]; then while read pid; do "
            "[ \"$(readlink /proc/$pid/exe)\" != /tmp/me-gvproxy-http/server ] || kill $pid; done < /tmp/me-gvproxy-http/pids; "
            "rm -f /tmp/me-gvproxy-http/pids /tmp/me-gvproxy-http/ready /tmp/me-gvproxy-http/server "
            "/tmp/me-gvproxy-http/server.log /tmp/me-gvproxy-http/main.go; rmdir /tmp/me-gvproxy-http; fi")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
