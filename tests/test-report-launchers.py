"""Loopback-only launcher integration; ngrok is simulated, no public tunnel."""
from pathlib import Path
import os
import json
import socket
import signal
import hashlib
import subprocess
import sys
import tempfile
import time
import urllib.request
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = Path(os.environ.get('REPORT_TEST_PLUGINS', ROOT / 'plugins'))


class LauncherTests(unittest.TestCase):
    def exercise(self, plugin, mode):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            project = fixture / 'project'
            nested = project / 'nested'
            nested.mkdir(parents=True)
            if plugin == 'diff-sharing':
                subprocess.run(['git', 'init', '-q', str(project)], check=True, capture_output=True)
            home = fixture / 'home'
            digest = hashlib.md5(str(project.resolve()).encode()).hexdigest()
            output = home / '.cache' / ('diff-reports' if plugin == 'diff-sharing' else 'test-reports') / digest
            output.mkdir(parents=True)
            (output / "index.html").write_text("owned-report-fixture")
            generation = '1' * 32
            if mode == 'local':
                first = output / 'generations' / generation
                first.mkdir(parents=True)
                (first / 'index.html').write_text('owned-report-fixture')
                (first / 'asset.css').write_text('old-generation-asset')
                (output / 'current.json').write_text(json.dumps({'generation': generation}))
            binary = fixture / "bin"
            binary.mkdir()
            (binary / "ngrok").write_text("#!/bin/bash\necho attempted > \"$TUNNEL_LOG\"\n"
                                           "if [ \"$TUNNEL_BLOCK\" = 1 ]; then while :; do sleep 0.1; done; fi\nexit 41\n")
            (binary / "ngrok").chmod(0o755)
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            log_file = fixture / "output.log"
            script = PLUGINS / plugin / "scripts/start-ngrok.sh"
            env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ["PATH"],
                       HOME=str(home), USERPROFILE=str(home),
                       TUNNEL_BLOCK="1" if mode == "tunnel" else "0",
                       TUNNEL_LOG=(fixture / "tunnel.log").as_posix())
            env.pop('REPORT_OUTPUT_DIR', None)
            args = [sys.executable, str(script.with_suffix('.py')), '--port', str(port)]
            if plugin == 'test-report-sharing':
                args += ['--project-dir', '..']
            if mode == "local":
                args.append("--local-only")
            http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with log_file.open("wb") as log:
                process = subprocess.Popen(args, env=env, stdout=log, stderr=log, cwd=nested,
                                           creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
                try:
                    deadline = time.monotonic() + 15
                    while True:
                        self.assertIsNone(process.poll(), log_file.read_text(errors="replace"))
                        try:
                            with http.open(f"http://127.0.0.1:{port}/", timeout=1) as response:
                                self.assertEqual(response.read(), b"owned-report-fixture")
                            if mode == "local" or (fixture / "tunnel.log").exists():
                                break
                        except OSError:
                            pass
                        self.assertLess(time.monotonic(), deadline, log_file.read_text(errors="replace"))
                        time.sleep(0.1)
                    if mode == "local":
                        self.assertFalse((fixture / "tunnel.log").exists())
                    if mode == 'local':
                        second_id = '2' * 32
                        second = output / 'generations' / second_id
                        second.mkdir()
                        (second / 'index.html').write_text('replacement-fixture')
                        pending = output / 'next.json'
                        pending.write_text(json.dumps({'generation': second_id}))
                        os.replace(pending, output / 'current.json')
                        with http.open(f'http://127.0.0.1:{port}/', timeout=2) as response:
                            self.assertEqual(response.read(), b'replacement-fixture')
                        with http.open(f'http://127.0.0.1:{port}/generations/{generation}/asset.css', timeout=2) as response:
                            self.assertEqual(response.read(), b'old-generation-asset')
                finally:
                    if process.poll() is None:
                        process.send_signal(signal.CTRL_BREAK_EVENT if os.name == 'nt' else signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                        raise
            self.assertEqual(process.returncode, 149 if os.name == 'nt' else 143)
            with socket.socket() as probe:
                probe.settimeout(1)
                self.assertNotEqual(probe.connect_ex(("127.0.0.1", port)), 0, "Owned server survived launcher exit")


def launcher_case(plugin, mode):
    def test(self):
        self.exercise(plugin, mode)
    return test


for plugin in ('diff-sharing', 'test-report-sharing'):
    for mode in ('local', 'failed-auth', 'tunnel'):
        setattr(LauncherTests, 'test_' + plugin.replace('-', '_') + '_' + mode.replace('-', '_'),
                launcher_case(plugin, mode))


if __name__ == '__main__':
    # Preserve the CI plugin filter while accepting normal unittest options.
    plugins = [arg for arg in sys.argv[1:] if arg in ('diff-sharing', 'test-report-sharing')]
    if plugins:
        selected = ['test_' + name.replace('-', '_') + '_' for name in plugins]
        for name in list(vars(LauncherTests)):
            if name.startswith('test_') and not any(name.startswith(prefix) for prefix in selected):
                delattr(LauncherTests, name)
    unittest.main(argv=[arg for arg in sys.argv if arg not in plugins])
