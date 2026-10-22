"""Forward readiness and Appium ownership at failed handoff boundaries."""
import json
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import socket
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from test_guest_transport import GuestTransport
from test_appium_proxy import AppiumProxy, CleanupUncertain, Creation, RelayState
from test_environment import guest_lease


class OwnershipTests(unittest.TestCase):
    def test_close_rejects_new_work_before_waiting_for_server_shutdown(self):
        with tempfile.TemporaryDirectory() as folder:
            proxy = AppiumProxy('http://127.0.0.1:1', None,
                                {'launch': {}, 'cleanup_roots': []}, Path(folder))
            proxy.launch = Mock()
            proxy.start()
            shutdown = proxy.server.shutdown
            def closing():
                with self.assertRaisesRegex(RuntimeError, 'relay is closed'):
                    self.create(proxy)
                proxy.launch.prepare.assert_not_called()
                shutdown()
            with patch.object(proxy.server, 'shutdown', side_effect=closing) as observed:
                proxy.close()
            observed.assert_called_once()
            proxy.launch.close.assert_called_once()

    def test_unstarted_proxy_closes_socket_without_waiting_for_server_shutdown(self):
        with tempfile.TemporaryDirectory() as folder:
            proxy = AppiumProxy('http://127.0.0.1:1', None,
                                {'launch': {}, 'cleanup_roots': []}, Path(folder))
            proxy.launch = Mock()
            with patch.object(proxy.server, 'shutdown') as shutdown, \
                    patch.object(proxy.thread, 'join') as join:
                proxy.close()
            shutdown.assert_not_called()
            join.assert_not_called()
            self.assertEqual(proxy.server.fileno(), -1)
            proxy.launch.close.assert_called_once()

    def test_shell_free_channel_waits_for_every_forward_acknowledgement(self):
        with tempfile.TemporaryDirectory() as folder:
            transport = GuestTransport({'os': 'windows', 'ssh_user': 'fixture',
                'access_key': 'fixture-key', 'ssh_port': 2222}, folder)
            child = Mock(); child.poll.return_value = None; child.stdin = None
            error = None

            def start(command, **kwargs):
                nonlocal error
                self.assertIn('-N', command)
                self.assertEqual(command[-1], 'fixture@127.0.0.1')
                self.assertEqual(kwargs['stdin'], subprocess.DEVNULL)
                error = kwargs['stderr']
                error.write(b'Entering interactive session.\nLocal forwarding listening on 127.0.0.1 port 4000\nremote forward success for: listen 5000\n')
                error.flush()
                return child

            def acknowledge(_):
                with Path(error.name).open('ab') as stream:
                    stream.write(b'remote forward success for: listen 5001\n')

            with patch('test_guest_transport.subprocess.Popen', side_effect=start), \
                    patch('test_guest_transport.time.sleep', side_effect=acknowledge) as sleep:
                result = transport.forward(['-L', '127.0.0.1:4000:127.0.0.1:4000',
                    '-R', '127.0.0.1:5000:127.0.0.1:5000', '-R', '127.0.0.1:5001:127.0.0.1:5001'])
            self.assertIs(result, child)
            sleep.assert_called_once()
            child.terminate.assert_not_called()
            transport.close()
            child.terminate.assert_called_once()

    def test_missing_forward_acknowledgement_stops_only_the_owned_channel(self):
        with tempfile.TemporaryDirectory() as folder:
            transport = GuestTransport({'os': 'windows', 'ssh_user': 'fixture',
                'access_key': 'fixture-key', 'ssh_port': 2222}, folder)
            child = Mock(); child.poll.return_value = None; child.stdin = None
            with patch('test_guest_transport.subprocess.Popen', return_value=child), \
                    patch('test_guest_transport.time.monotonic', side_effect=[0, 1, 16]), \
                    patch('test_guest_transport.time.sleep'):
                with self.assertRaisesRegex(RuntimeError, 'forwarding failed'):
                    transport.forward(['-R', '127.0.0.1:5000:127.0.0.1:5000'])
            child.terminate.assert_called_once()
            child.wait.assert_called_once_with(timeout=5)

    def proxy(self):
        proxy = AppiumProxy.__new__(AppiumProxy)
        proxy.sessions = set()
        proxy.creation = Creation.IDLE
        proxy.relay_state = RelayState.OPEN
        proxy.launch = Mock()
        proxy.request = Mock()
        return proxy

    def create(self, proxy):
        return proxy.relay('POST', '/session', json.dumps({'desiredCapabilities': {}}).encode())

    def test_failed_output_handoff_deletes_the_unpublished_session(self):
        proxy = self.proxy()
        proxy.request.side_effect = [(200, {}, b'{"value":{"sessionId":"owned"}}'), (200, {}, b'{}')]
        proxy.launch.collect.side_effect = RuntimeError('output transport failed')
        with self.assertRaisesRegex(RuntimeError, 'output transport failed'):
            self.create(proxy)
        self.assertEqual(proxy.sessions, set())
        self.assertEqual(proxy.request.call_args.args, ('DELETE', '/session/owned', b''))
        proxy.launch.stop_forwarding.assert_called_once()

    def test_failed_rollback_retains_session_and_forwarding_for_cleanup(self):
        for response in [(500, {}, b'{}'), OSError('lost cleanup response')]:
            with self.subTest(response=response):
                proxy = self.proxy()
                proxy.request.side_effect = [(200, {}, b'{"sessionId":"owned"}'), response]
                proxy.launch.collect.side_effect = RuntimeError('output transport failed')
                with self.assertRaises(CleanupUncertain): self.create(proxy)
                self.assertEqual(proxy.sessions, {'owned'})
                proxy.launch.stop_forwarding.assert_not_called()

    def test_confirmed_delete_releases_ownership_even_if_diagnostics_fail(self):
        for status in [200, 404]:
            with self.subTest(status=status):
                proxy = self.proxy(); proxy.sessions.add('owned')
                proxy.request.return_value = (status, {}, b'{}')
                proxy.launch.collect.side_effect = RuntimeError('diagnostic transport failed')
                with self.assertRaisesRegex(RuntimeError, 'diagnostic transport failed'):
                    proxy.relay('DELETE', '/session/owned', b'')
                self.assertEqual(proxy.sessions, set())
                proxy.launch.stop_forwarding.assert_called_once()

    def test_rejected_delete_keeps_live_session_ownership(self):
        proxy = self.proxy(); proxy.sessions.add('owned')
        proxy.request.return_value = (500, {}, b'{}')
        self.assertEqual(proxy.relay('DELETE', '/session/owned', b'')[0], 500)
        self.assertEqual(proxy.sessions, {'owned'})
        proxy.launch.stop_forwarding.assert_not_called()

    def test_rejected_creation_stops_prepared_forwarding(self):
        proxy = self.proxy(); proxy.request.return_value = (400, {}, b'{}')
        self.assertEqual(self.create(proxy)[0], 400)
        self.assertEqual(proxy.sessions, set())
        proxy.launch.stop_forwarding.assert_called_once()

    def closable_proxy(self):
        proxy = self.proxy()
        proxy.server = Mock(); proxy.thread = Mock(); proxy.lock = threading.Lock()
        return proxy

    def test_lost_creation_response_retains_lease_and_private_inputs(self):
        for error in [TimeoutError('response lost'), ConnectionResetError('response lost')]:
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as folder:
                proxy = self.closable_proxy(); proxy.request.side_effect = error
                with self.assertRaises(CleanupUncertain):
                    with guest_lease(folder):
                        try:
                            with self.assertRaises(CleanupUncertain): self.create(proxy)
                            self.assertEqual(proxy.creation, Creation.UNKNOWN)
                            with self.assertRaisesRegex(RuntimeError, 'One desktop session'):
                                self.create(proxy)
                        finally:
                            proxy.close()
                owner = json.loads((Path(folder) / 'test-environment.lock/owner.json').read_text())
                self.assertEqual(owner['phase'], 'cleanup-uncertain')
                proxy.launch.close.assert_not_called()
                proxy.launch.stop_forwarding.assert_not_called()
                self.assertEqual(proxy.request.call_count, 1)

    def test_unusable_success_response_retains_creation_uncertainty(self):
        for body in [b'invalid json', b'{"value":{}}', b'{"value":{"sessionId":42}}']:
            with self.subTest(body=body):
                proxy = self.closable_proxy(); proxy.request.return_value = (200, {}, body)
                with self.assertRaises(CleanupUncertain): self.create(proxy)
                with self.assertRaises(CleanupUncertain): proxy.close()
                self.assertEqual(proxy.creation, Creation.UNKNOWN)
                proxy.launch.close.assert_not_called()

    def test_interrupted_inflight_creation_cannot_release_lease(self):
        proxy = self.closable_proxy(); proxy.request.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt): self.create(proxy)
        self.assertEqual(proxy.creation, Creation.REQUESTING)
        with self.assertRaises(CleanupUncertain): proxy.close()
        proxy.launch.close.assert_not_called()

    def test_preparation_failure_does_not_mark_remote_creation_uncertain(self):
        proxy = self.closable_proxy(); proxy.launch.prepare.side_effect = ValueError('invalid launch')
        with self.assertRaises(ValueError): self.create(proxy)
        self.assertEqual(proxy.creation, Creation.IDLE)
        proxy.request.assert_not_called()
        proxy.close(); proxy.launch.close.assert_called_once()

    def test_successful_creation_is_owned_and_deleted_before_local_cleanup(self):
        proxy = self.closable_proxy()
        proxy.request.side_effect = [(200, {}, b'{"value":{"sessionId":"owned"}}'), (200, {}, b'{}')]
        self.create(proxy)
        self.assertEqual(proxy.creation, Creation.IDLE)
        self.assertEqual(proxy.sessions, {'owned'})
        proxy.close()
        self.assertEqual(proxy.request.call_args.args, ('DELETE', '/session/owned', b''))
        self.assertEqual(proxy.sessions, set())
        proxy.launch.close.assert_called_once()

    def test_http_disconnect_after_remote_creation_retains_guest_lease(self):
        created = threading.Event()

        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *_args): pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                created.set()  # Model a committed session whose response is lost.
                self.close_connection = True

        upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        worker = threading.Thread(target=upstream.serve_forever, daemon=True); worker.start()
        self.addCleanup(worker.join, 5)
        self.addCleanup(upstream.server_close); self.addCleanup(upstream.shutdown)
        with tempfile.TemporaryDirectory() as folder:
            proxy = AppiumProxy(f'http://127.0.0.1:{upstream.server_port}', None,
                                {'launch': {}, 'cleanup_roots': []}, Path(folder))
            proxy.launch = Mock(); proxy.launch.prepare.return_value = {}
            proxy.start()
            with self.assertRaises(CleanupUncertain):
                with guest_lease(folder):
                    try:
                        connection = http.client.HTTPConnection('127.0.0.1', proxy.server.server_port, timeout=5)
                        try:
                            connection.request('POST', '/session', b'{"desiredCapabilities":{}}')
                            response = connection.getresponse()
                            self.assertEqual(response.status, 502)
                            response.read()
                            self.assertTrue(created.is_set())
                        finally:
                            connection.close()
                    finally:
                        proxy.close()
            self.assertEqual(json.loads((Path(folder) / 'test-environment.lock/owner.json').read_text())['phase'],
                             'cleanup-uncertain')
            proxy.launch.close.assert_not_called()

    def test_request_body_arriving_after_close_cannot_launch_an_application(self):
        with tempfile.TemporaryDirectory() as folder:
            proxy = AppiumProxy('http://127.0.0.1:1', None,
                                {'launch': {}, 'cleanup_roots': []}, Path(folder))
            proxy.launch = Mock(); proxy.request = Mock()
            accepted = threading.Event()
            handler = proxy.server.RequestHandlerClass; original = handler.setup
            def setup(request):
                original(request); accepted.set()
            handler.setup = setup
            proxy.start()
            with socket.create_connection(('127.0.0.1', proxy.server.server_port), timeout=5) as client:
                body = b'{"desiredCapabilities":{}}'
                client.sendall(f'POST /session HTTP/1.0\r\nContent-Length: {len(body)}\r\n\r\n'.encode())
                self.assertTrue(accepted.wait(5))
                proxy.close()
                client.sendall(body)
                response = http.client.HTTPResponse(client); response.begin()
                self.assertEqual(response.status, 502); response.read(); response.close()
            proxy.launch.prepare.assert_not_called(); proxy.request.assert_not_called()
            proxy.launch.close.assert_called_once()
            self.assertEqual(proxy.sessions, set())


if __name__ == '__main__': unittest.main()
