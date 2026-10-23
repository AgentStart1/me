"""Loopback WebDriver relay with launch-time transparent file/service transport."""
import http.client
from contextlib import nullcontext
from enum import Enum, auto
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib.parse import urlsplit

from test_java_launch import JavaLaunch
from test_environment_owner import CleanupUncertain
from test_cancellation import current_cancellation


class Creation(Enum):
    IDLE = auto()
    REQUESTING = auto()
    UNKNOWN = auto()


class RelayState(Enum):
    OPEN = auto()
    CLOSED = auto()


def capabilities(body):
    data = json.loads(body)
    if 'capabilities' not in data:
        return data['desiredCapabilities']
    caps = data['capabilities']
    matches = caps.get('firstMatch', [{}])
    if len(matches) != 1:
        raise ValueError('Transparent launch proxy requires one capability candidate')
    return {**caps.get('alwaysMatch', {}), **matches[0]}


class AppiumProxy:
    def __init__(self, upstream, transport, config, workspace):
        self.upstream = urlsplit(upstream)
        self.launch = JavaLaunch(transport, config, workspace)
        self.cancellation = current_cancellation()
        self.lock = threading.Lock()
        self.sessions = set()
        self.creation = Creation.IDLE
        self.relay_state = RelayState.OPEN
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass  # WebDriver bodies may contain credentials and typed values.

            def do_GET(self): self.relay()
            def do_POST(self): self.relay()
            def do_DELETE(self): self.relay()

            def relay(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                try:
                    status, headers, response = owner.dispatch(self.command, self.path, body)
                except BaseException as error:
                    status, headers = 502, {'Content-Type': 'application/json'}
                    message = ('Test environment proxy failed: ' + str(error) if isinstance(error, Exception)
                               else 'Test environment request interrupted.')
                    response = json.dumps({'value': {'error': 'unknown error', 'message':
                        message, 'stacktrace': ''}}).encode()
                self.send_response(status)
                for name, value in headers.items():
                    if name.lower() not in {'content-length', 'transfer-encoding', 'connection', 'keep-alive'}:
                        self.send_header(name, value)
                self.send_header('Content-Length', str(len(response)))
                self.end_headers()
                self.wfile.write(response)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self):
        return f'http://127.0.0.1:{self.server.server_port}'

    def start(self):
        self.thread.start()

    def request(self, method, path, body):
        connection = http.client.HTTPConnection(self.upstream.hostname, self.upstream.port, timeout=180)
        try:
            connection.request(method, path, body=body, headers={'Content-Type': 'application/json'})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def dispatch(self, method, path, body):
        # Reports are published before completion and lock release, independently
        # of the HTTP error conversion performed by Handler.
        with self.lock:
            with self.cancellation.worker() if self.cancellation is not None else nullcontext():
                try:
                    return self.relay(method, path, body)
                except BaseException as error:
                    if self.cancellation is not None and isinstance(error, CleanupUncertain):
                        self.cancellation.report_cleanup(error)
                    raise

    def relay(self, method, path, body):
        if self.relay_state is RelayState.CLOSED:
            raise RuntimeError('Test environment relay is closed')
        creating = method == 'POST' and path.rstrip('/') == '/session'
        if creating:
            if self.sessions or self.creation is not Creation.IDLE:
                raise RuntimeError('One desktop session at a time is allowed per guest environment')
            prepared = self.launch.prepare(capabilities(body))
            if isinstance(prepared, dict):
                body = json.dumps({'capabilities': {'alwaysMatch': prepared, 'firstMatch': [{}]}}).encode()
        if creating:
            self.creation = Creation.REQUESTING
        try:
            status, headers, response = self.request(method, path, body)
            if creating and status < 300:
                data = json.loads(response)
                identifier = data.get('sessionId') or data.get('value', {}).get('sessionId')
                if not isinstance(identifier, str) or not identifier:
                    raise ValueError('Appium returned no valid session ID')
                self.sessions.add(identifier)
            if creating:
                self.creation = Creation.IDLE
        except Exception as error:
            if creating:
                # A lost/malformed response cannot establish whether the remote side committed.
                self.creation = Creation.UNKNOWN
                raise CleanupUncertain('Appium creation outcome is unknown; retain the guest test lease') from error
            raise
        if creating and status < 300:
            try:
                self.launch.collect()  # Outputs must exist before handing the session to the client.
            except Exception:
                try:
                    cleanup_status, _, _ = self.request('DELETE', '/session/' + identifier, b'')
                    if cleanup_status >= 300 and cleanup_status != 404:
                        raise CleanupUncertain('Created Appium session rollback was not confirmed')
                    self.sessions.discard(identifier)
                    self.launch.stop_forwarding()
                except Exception as cleanup:
                    raise CleanupUncertain('Appium handoff failed and rollback is uncertain') from cleanup
                raise
        if creating and status >= 300:
            self.launch.stop_forwarding()
        identifier = path.rstrip('/').split('/')[-1]
        if method == 'DELETE' and identifier in self.sessions and (status < 300 or status == 404):
            self.sessions.remove(identifier)
            self.launch.stop_forwarding()
        if path.endswith('/source') or method == 'DELETE':
            self.launch.collect()
        return status, headers, response

    def close(self):
        # Stop admission before waiting for an active worker or server shutdown.
        self.relay_state = RelayState.CLOSED
        if self.thread.ident is not None:
            self.server.shutdown()
        self.server.server_close()
        if self.thread.ident is not None:
            self.thread.join(timeout=5)
        with self.lock:
            # A worker already inside relay must finish before session cleanup.
            try:
                if self.creation is not Creation.IDLE:
                    raise CleanupUncertain('Appium creation outcome is unknown; inspect the guest before releasing its lease')
                for identifier in list(self.sessions):
                    status, _, _ = self.request('DELETE', '/session/' + identifier, b'')
                    if status >= 300 and status != 404:
                        raise RuntimeError('Guest Appium session shutdown was not confirmed')
                    self.sessions.discard(identifier)
                self.launch.close()
            except Exception as error:
                raise CleanupUncertain('Guest cleanup could not be confirmed; retain its test lease') from error
