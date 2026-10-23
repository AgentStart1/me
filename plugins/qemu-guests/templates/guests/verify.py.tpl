"""Read-only Appium service acceptance; no container backend is required."""
import json
import urllib.request
from pathlib import Path
import re
import subprocess
if Path('/opt/qemu-guests/desktop.json').exists():
    expected = json.loads(Path('/opt/qemu-guests/desktop.json').read_text())
    actual = json.loads(Path('/opt/qemu-guests/state/desktop-ready.json').read_text())
    assert actual['width'] == expected['width'] and actual['height'] == expected['height']
    subprocess.run(['pgrep', '-u', '{{USER}}', '-x', 'xfce4-session'], check=True, capture_output=True)
    requirements = json.loads(Path('/opt/qemu-guests/runtime-requirements.json').read_text())
    version = subprocess.check_output(['java', '-version'], stderr=subprocess.STDOUT).decode()
    assert int(re.search(r'version "(\d+)', version)[1]) == requirements['java'], 'Java runtime version mismatch'
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open('http://127.0.0.1:4723/status', timeout=3) as response:
    assert json.load(response)['value']['ready'], 'Appium not ready'
