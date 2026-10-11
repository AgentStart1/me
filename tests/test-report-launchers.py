"""Loopback-only launcher integration; ngrok is simulated, no public tunnel."""
from pathlib import Path
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def exercise(plugin, mode):
    bash = shutil.which("bash")
    if os.name == "nt":
        native = Path(bash).parent.parent / "usr/bin/bash.exe"
        if native.exists():
            bash = str(native)
    with tempfile.TemporaryDirectory() as directory:
        fixture = Path(directory)
        (fixture / "index.html").write_text("owned-report-fixture")
        binary = fixture / "bin"
        binary.mkdir()
        (binary / "ngrok").write_text("#!/bin/bash\necho attempted > \"$TUNNEL_LOG\"\n"
                                       "if [ \"$TUNNEL_BLOCK\" = 1 ]; then while :; do sleep 0.1; done; fi\nexit 41\n")
        (binary / "ngrok").chmod(0o755)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        pid_file = fixture / "driver.pid"
        log_file = fixture / "output.log"
        script = ROOT / "plugins" / plugin / "scripts/start-ngrok.sh"
        env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ["PATH"],
                   PYTHON_COMMAND=Path(sys.executable).as_posix(),
                   REPORT_OUTPUT_DIR=fixture.as_posix(), DRIVER_PID=pid_file.as_posix(),
                   TUNNEL_BLOCK="1" if mode == "tunnel" else "0",
                   TUNNEL_LOG=(fixture / "tunnel.log").as_posix())
        args = [bash, "-c", 'echo $$ > "$DRIVER_PID"; exec bash "$@"', "fixture",
                script.as_posix(), "--port", str(port)]
        if mode == "local":
            args.append("--local-only")
        http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with log_file.open("wb") as log:
            process = subprocess.Popen(args, env=env, stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 15
                while True:
                    assert process.poll() is None, log_file.read_text(errors="replace")
                    try:
                        with http.open(f"http://127.0.0.1:{port}/", timeout=1) as response:
                            assert response.read() == b"owned-report-fixture"
                        if mode == "local" or (fixture / "tunnel.log").exists():
                            break
                    except OSError:
                        pass
                    assert time.monotonic() < deadline, log_file.read_text(errors="replace")
                    time.sleep(0.1)
                assert mode != "local" or not (fixture / "tunnel.log").exists()
            finally:
                if process.poll() is None and pid_file.exists():
                    subprocess.run([bash, "-c", 'kill -TERM "$(cat "$1")"', "stop", pid_file.as_posix()],
                                   env=env, check=True, capture_output=True)
                process.wait(timeout=10)
        assert process.returncode == 143, process.returncode
        with socket.socket() as probe:
            probe.settimeout(1)
            assert probe.connect_ex(("127.0.0.1", port)) != 0, "Owned server survived launcher exit"
        print(f"PASS: {plugin} {mode}, working loopback response and owned-server cleanup")


if __name__ == "__main__":
    plugins = sys.argv[1:] or ["diff-sharing", "test-report-sharing"]
    for plugin in plugins:
        for mode in ("local", "failed-auth", "tunnel"):
            exercise(plugin, mode)
