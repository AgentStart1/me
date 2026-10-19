"""Read-only acceptance of API forwarding and every guest-side TCP listener."""
import json
import socket
import urllib.request

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open('http://127.0.0.1:2375/version', timeout=3) as response:
    assert json.load(response)['Os'] == 'linux'
for port in range({{POOL_START}}, {{POOL_END}} + 1):
    with socket.create_connection(('127.0.0.1', port), timeout=1):
        pass
