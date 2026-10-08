# /// script
# requires-python = ">=3.10"
# dependencies = ["openai-mcp-extensions==0.1.0", "mcp==2.2.0"]
# ///
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import status
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

CONTAINER = {"Id": "abc123def456789", "Names": ["/<script>alert(1)</script>"], "Image": "alpine:latest", "State": "running", "Status": "Up 1 minute (healthy)", "Ports": [{"IP": "127.0.0.1", "PublicPort": 20000, "PrivatePort": 80, "Type": "tcp"}], "Env": ["SECRET=never-render"], "Labels": {"secret": "private"}}


@contextmanager
def docker_api(routes=None):
    routes = routes or {"/_ping": b"OK", "/version": {"Version": "28.0.0"}, "/containers/json?all=1": [CONTAINER]}
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            payload = routes.get(self.path)
            if payload is None:
                self.send_error(503)
                return
            if payload == "redirect":
                self.send_response(302)
                self.send_header("Location", "http://example.invalid/")
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(payload if isinstance(payload, bytes) else json.dumps(payload).encode())
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def profile(directory, port):
    path = Path(directory) / "custom.profile"
    path.write_text(f"VM_NAME=alpine-test\nVM_MEMORY=1024\nVM_CPUS=2\nVM_ACCELERATOR=auto\nSSH_PORT=2222\nDOCKER_DAEMON_PORT={port}\n")
    return path


class StatusTests(unittest.TestCase):
    def test_profile_rejects_expansion_path_traversal_and_invalid_port(self):
        with tempfile.TemporaryDirectory() as directory:
            path = profile(directory, 2375)
            for line in ["VM_NAME=../outside", "SSH_PORT=0", "DOCKER_DAEMON_PORT=65536", "VM_MEMORY=$(touch secret)", "VM_NAME=`whoami`"]:
                original = profile(directory, 2375).read_text()
                path.write_text(original + line + "\n")
                with self.assertRaises(ValueError): status.read_profile(path)

    def test_docker_probe_bypasses_proxy_and_redacts_private_metadata(self):
        with docker_api() as (port, requests), patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:1", "http_proxy": "http://127.0.0.1:1", "NO_PROXY": "", "no_proxy": ""}):
            health, containers = status.docker_health(port)
            self.assertEqual(health["state"], "healthy")
            self.assertEqual(health["version"], "28.0.0")
            self.assertEqual(containers["items"][0]["ports"], ["127.0.0.1:20000 → 80/tcp"])
            self.assertNotIn("never-render", json.dumps(containers))
            self.assertNotIn("Labels", json.dumps(containers))
            self.assertEqual(requests, ["/_ping", "/version", "/containers/json?all=1"])

    def test_empty_unavailable_and_partial_health_are_distinct(self):
        with docker_api({"/_ping": b"OK", "/version": {"Version": "28"}, "/containers/json?all=1": []}) as (port, _):
            health, containers = status.docker_health(port)
            self.assertEqual(containers, {"state": "available", "items": []})
        with docker_api({"/_ping": b"OK"}) as (port, _):
            health, containers = status.docker_health(port)
            self.assertEqual(health["state"], "healthy")
            self.assertEqual(containers["state"], "unavailable")
        with patch.object(status, "docker_get", side_effect=socket.timeout):
            health, containers = status.docker_health(2375)
            self.assertEqual(health["state"], "unreachable")
            self.assertEqual(health["detail"], "Probe timed out")

    def test_redirects_and_malformed_or_large_responses_fail_closed(self):
        with docker_api({"/_ping": "redirect"}) as (port, _):
            with self.assertRaises(ValueError): status.docker_get(port, "/_ping")
        with docker_api({"/_ping": b"OK", "/version": {}, "/containers/json?all=1": b"not json"}) as (port, _):
            self.assertEqual(status.docker_health(port)[1]["state"], "unavailable")
        with docker_api({"/version": b"x" * (status.MAX_RESPONSE + 1)}) as (port, _):
            with self.assertRaises(ValueError): status.docker_get(port, "/version")

    def test_msys_pid_is_translated_and_native_identity_is_verified(self):
        with patch.object(status.os, "name", "nt"), patch.object(status.subprocess, "run") as run:
            run.side_effect = [subprocess.CompletedProcess([], 0, "PID PPID PGID WINPID\n1234 1 1234 5678 qemu\n", ""),
                               subprocess.CompletedProcess([], 0, "qemu-system-x86_64\n", "")]
            self.assertEqual(status.process_state(1234), "running")
            self.assertIn("Get-Process -Id 5678", run.call_args.args[0][-1])
            run.side_effect = [subprocess.CompletedProcess([], 0, "1234 1 1234 5678 qemu\n", ""),
                               subprocess.CompletedProcess([], 0, "notepad\n", "")]
            self.assertEqual(status.process_state(1234), "stopped")

    def test_windows_process_identity_and_missing_probe_are_distinct(self):
        with patch.object(status.os, "name", "nt"), patch.object(status.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, "qemu-system-x86_64\n", "")
            self.assertEqual(status.process_state(1234), "running")
            run.return_value = subprocess.CompletedProcess([], 0, "notepad\n", "")
            self.assertEqual(status.process_state(1234), "stopped")
            run.side_effect = FileNotFoundError
            self.assertEqual(status.process_state(1234), "unknown")

    def test_accelerator_reader_exposes_only_the_mode(self):
        with patch.object(status.os, "name", "nt"), patch.object(status.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, 'qemu-system-x86_64 -accel whpx -drive file=C:/private/disk.qcow2', '')
            self.assertEqual(status.process_accelerator(1234), "whpx")
            run.return_value = subprocess.CompletedProcess([], 0, 'qemu-system-x86_64 -accel unexpected', '')
            self.assertIsNone(status.process_accelerator(1234))

    def test_invalid_ping_is_unhealthy_not_unreachable(self):
        with docker_api({"/_ping": b"Unexpected response"}) as (port, _):
            self.assertEqual(status.docker_health(port)[0]["state"], "unhealthy")

    def test_reused_pid_does_not_report_qemu_running(self):
        self.assertEqual(status.process_state(os.getpid()), "stopped")
        self.assertEqual(status.process_state(None), "stopped")

    def test_snapshot_does_not_create_or_modify_state_and_warns_about_unverified_services(self):
        with tempfile.TemporaryDirectory() as directory:
            path = profile(directory, 2375)
            base = Path(directory) / "state"
            with patch.dict(os.environ, {"QEMU_STATUS_PROFILE": str(path), "QEMU_ALPINE_BASE_DIR": str(base)}), \
                 patch.object(status, "ssh_health", return_value={"state": "unreachable", "detail": "Unreachable"}), \
                 patch.object(status, "docker_health", return_value=({"state": "healthy", "detail": "OK"}, {"state": "available", "items": []})):
                snapshot = status.collect_status()
            self.assertFalse(base.exists())
            self.assertEqual(snapshot["vm"]["state"], "stopped")
            self.assertFalse(snapshot["vm"]["provisioned"])
            self.assertTrue(snapshot["warnings"])


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_global_and_thread_entrypoints_resource_and_read_only_tool(self):
        with tempfile.TemporaryDirectory() as directory, docker_api() as (port, _):
            path = profile(directory, port)
            parameters = StdioServerParameters(command=sys.executable, args=[str(ROOT / "scripts/status-server.py")], env={**os.environ, "QEMU_STATUS_PROFILE": str(path), "QEMU_ALPINE_BASE_DIR": str(Path(directory) / "state"), "PYTHONDONTWRITEBYTECODE": "1"})
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    tools = (await client.list_tools()).tools
                    self.assertEqual([tool.name for tool in tools], ["qemu_docker_status"])
                    tool = tools[0]
                    self.assertTrue(tool.annotations.read_only_hint)
                    self.assertFalse(tool.annotations.destructive_hint)
                    self.assertEqual(tool.meta["openai/ui"]["entrypoints"], [{"type": "global"}, {"type": "thread"}])
                    uri = tool.meta["ui"]["resourceUri"]
                    resource = await client.read_resource(uri)
                    self.assertEqual(resource.contents[0].mime_type, "text/html;profile=mcp-app")
                    self.assertIn("VM &amp; Containers", resource.contents[0].text)
                    self.assertNotIn("/* PANEL_SCRIPT */", resource.contents[0].text)
                    result = await client.call_tool("qemu_docker_status", {})
                    self.assertFalse(result.is_error)
                    snapshot = result.structured_content
                    self.assertEqual(snapshot["services"]["docker"]["state"], "healthy")
                    self.assertEqual(len(snapshot["containers"]["items"]), 1)
                    self.assertFalse((Path(directory) / "state").exists())


if __name__ == "__main__": unittest.main()
