"""Bounded read-only QMP screen capture for a registered, verified work guest."""
import base64
import json
from pathlib import Path
import re
import socket
import tempfile
import time

from guest_registry import entries, state
from process_identity import identity, owns_listeners


class Qmp:
    def __init__(self, port):
        self.socket = socket.create_connection(('127.0.0.1', port), timeout=3)
        self.socket.settimeout(3)
        self.stream = self.socket.makefile('rwb')
        try:
            if 'QMP' not in self.read():
                raise ValueError('Invalid QMP greeting')
            self.execute('qmp_capabilities')
        except BaseException:
            self.close()
            raise

    def read(self):
        line = self.stream.readline(1024 * 1024)
        if not line.endswith(b'\n'):
            raise ValueError('Incomplete QMP response')
        return json.loads(line)

    def execute(self, command, arguments=None):
        request = {'execute': command}
        if arguments is not None:
            request['arguments'] = arguments
        self.stream.write(json.dumps(request).encode() + b'\r\n')
        self.stream.flush()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            response = self.read()
            if 'error' in response:
                raise RuntimeError('QMP command failed: ' + response['error'].get('class', 'unknown'))
            if 'return' in response:
                return response['return']
        raise TimeoutError('QMP response timed out')

    def close(self):
        self.stream.close()
        self.socket.close()


def capture(identifier):
    if not re.fullmatch('[a-f0-9]{24}', identifier):
        raise ValueError('Invalid guest identifier')
    item = next((entry for entry in entries() if entry['id'] == identifier), None)
    if item is None or not item['graphical']:
        raise ValueError('No registered graphical guest')
    phase, record = state(item)
    if phase not in {'booting', 'ready', 'paused'} or record is None:
        raise ValueError('Guest is not supervised and running')
    if not owns_listeners(record['pid'], {item['qmp_port']}):
        raise ValueError('QMP listener does not belong to this guest')
    # Temp files are private, bounded and removed even when capture fails. The
    # panel receives only PNG data, never a host path or a general QMP endpoint.
    with tempfile.TemporaryDirectory(prefix='screen-', dir=item['state_dir']) as temporary:
        path = Path(temporary) / 'screen.png'
        client = Qmp(item['qmp_port'])
        try:
            client.execute('screendump', {'filename': str(path), 'format': 'png'})
        finally:
            client.close()
        if identity(record['pid']) != record['identity']:
            raise ValueError('Guest process changed during capture')
        if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('Screen unavailable or exceeds capture limit')
        data = path.read_bytes()
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Invalid screen image')
    return {'guestId': identifier, 'mimeType': 'image/png', 'data': base64.b64encode(data).decode()}
