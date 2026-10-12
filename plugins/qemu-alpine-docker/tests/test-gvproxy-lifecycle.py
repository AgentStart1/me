"""Real upstream helper lifecycle/API tests, without starting or contacting a VM."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("control", ROOT / "scripts/gvproxy-control.py")
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def main():
    binary = Path(os.environ["GVPROXY_BINARY"]).resolve()
    with tempfile.TemporaryDirectory() as directory:
        state = Path(directory) / "state.json"
        transport, api = free_port(), free_port()
        command = [sys.executable, str(ROOT / "scripts/gvproxy-control.py")]
        start = command + ["start", "--binary", str(binary), "--state", str(state),
                           "--log", str(Path(directory) / "helper.log"),
                           "--transport", str(transport), "--api", str(api)]
        stop = command + ["stop", "--state", str(state)]
        # Different ports must not permit competing owners of the same state.
        contenders = [subprocess.Popen(start, stdout=subprocess.PIPE, stderr=subprocess.PIPE),
                      subprocess.Popen(start[:-4] + ["--transport", str(free_port()), "--api", str(free_port())],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)]
        codes = []
        for contender in contenders:
            contender.communicate(timeout=30)
            codes.append(contender.returncode)
        assert codes.count(0) == 1, codes
        subprocess.run(stop, check=True, capture_output=True)
        subprocess.run(start, check=True, capture_output=True)
        try:
            assert subprocess.run(start, capture_output=True).returncode != 0
            check = command + ["check", "--state", str(state), "--api", str(api), "--transport", str(transport)]
            assert subprocess.run(check, input=b"", capture_output=True).returncode == 0
            assert subprocess.run(check[:-1] + [str(free_port())], input=b"", capture_output=True).returncode != 0
            assert subprocess.run(check, input=b"1:1\n", capture_output=True).returncode != 0
            url = f"http://127.0.0.1:{api}/services/forwarder/"
            def request(action, port=None):
                payload = {"local": f"127.0.0.1:{port}", "remote": "192.168.127.2:80", "protocol": "tcp"}
                req = urllib.request.Request(url + action, data=json.dumps(payload).encode() if port else None,
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=5) as response:
                    return response.read()
            ports = []
            for _ in range(640):
                port = free_port()
                request("expose", port)
                ports.append(port)
            assert len(json.loads(request("all"))) == 640
            request("unexpose", ports[-1])
            assert len(json.loads(request("all"))) == 639
            with socket.socket() as conflict:
                conflict.bind(("127.0.0.1", ports[-1]))
                conflict.listen()
                try:
                    request("expose", ports[-1])
                except urllib.error.HTTPError:
                    pass
                else:
                    raise AssertionError("port collision accepted")
        finally:
            subprocess.run(stop, check=True, capture_output=True)
        assert not state.exists()
        # Exercise the actual batch startup path above the removed 512-port cap.
        batch_ports = ports[:600]
        mappings = "".join(f"{port}:80\n" for port in batch_ports).encode()
        subprocess.run(start + ["--configure"], input=mappings, check=True, capture_output=True)
        try:
            assert subprocess.run(check, input=mappings, capture_output=True).returncode == 0
        finally:
            subprocess.run(stop, check=True, capture_output=True)
        # A late bind failure cleans the helper and every earlier listener.
        with socket.socket() as conflict:
            conflict.bind(("127.0.0.1", batch_ports[-1]))
            conflict.listen()
            failed = subprocess.run(start + ["--configure"], input=mappings, capture_output=True)
            assert failed.returncode != 0
            assert not state.exists()
            with socket.socket() as released:
                if os.name != "nt":
                    released.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                released.bind(("127.0.0.1", batch_ports[0]))
        assert subprocess.run(start + ["--configure"], input=b"0:80\n", capture_output=True).returncode != 0
        assert not state.exists()
        with socket.socket() as conflict:
            if os.name != "nt":
                conflict.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            conflict.bind(("127.0.0.1", api))
            conflict.listen()
            assert subprocess.run(start, capture_output=True).returncode != 0
            assert not state.exists()
        # PID reuse must never allow signalling the unrelated process.
        state.write_text(json.dumps({"pid": os.getpid(), "identity": ["wrong-binary", 0]}))
        assert subprocess.run(stop, capture_output=True).returncode != 0
        state.unlink()
        for _ in range(2):
            subprocess.run(start, check=True, capture_output=True)
            subprocess.run(stop, check=True, capture_output=True)
    print("PASS: real gvproxy readiness, 640 registrations, 600-rule batch startup, partial failure cleanup, collisions, PID reuse refusal and restart")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        if error.stderr:
            print(error.stderr.decode(errors="replace"), file=sys.stderr)
        raise
