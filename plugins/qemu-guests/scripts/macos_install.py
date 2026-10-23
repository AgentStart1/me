"""Unattended Intel Recovery terminal handoff; no setup-assistant clicking."""
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time

from guest_screen import Qmp
from process_identity import identity, owns_listeners, write_record


def key_events(keys):
    return [{'type': 'key', 'data': {'down': down, 'key': {'type': 'qcode', 'data': key}}}
            for down in (True, False) for key in (keys if down else list(reversed(keys)))]


def press_keys(client, keys):
    # Recovery's USB keyboard misses releases batched with presses. Allow a
    # guest poll between transitions and before the following character.
    events = key_events(keys)
    try:
        client.execute('input-send-event', {'events': events[:len(keys)]})
        time.sleep(0.15)
    finally:
        client.execute('input-send-event', {'events': events[len(keys):]})
    time.sleep(0.15)


def terminal_ready(text):
    return re.search(r'(?:bash|zsh|sh)-[0-9.]+\s*[#%$]', text) is not None


def text_keys(text):
    punctuation = {' ': 'spc', '/': 'slash', '.': 'dot', '-': 'minus', '\n': 'ret'}
    result = []
    for char in text:
        if char in punctuation:
            result.append([punctuation[char]])
        elif char.isascii() and char.isalnum():
            result.append((['shift'] if char.isupper() else []) + [char.lower()])
        else:
            raise ValueError('Unsupported recovery command character')
    return result


class RecoveryInstaller:
    def __init__(self, config, home, record):
        self.config, self.home, self.record = config, Path(home), record
        self.marker = self.home / 'macos-install.json'
        saved = json.loads(self.marker.read_text())['phase'] if self.marker.exists() else None
        # A new QEMU process does not retain Recovery's open Terminal window.
        self.phase = 'installer-started' if saved == 'installer-started' else 'waiting-recovery'
        self.next_probe = 0

    def screen_text(self, client):
        with tempfile.TemporaryDirectory(prefix='recovery-', dir=self.home) as directory:
            image = Path(directory) / 'screen.png'
            client.execute('screendump', {'filename': str(image), 'format': 'png'})
            from PIL import Image
            with Image.open(image) as frame:
                enlarged = frame.resize((frame.width * 3, frame.height * 3))
                enlarged.save(image)
            result = subprocess.run([self.config['macos']['tesseract'], str(image), 'stdout', '--psm', '11'],
                                    capture_output=True, text=True, timeout=10, check=True)
            return result.stdout.lower()

    def tick(self):
        if self.phase == 'installer-started' or time.monotonic() < self.next_probe:
            return
        self.next_probe = time.monotonic() + 5
        if identity(self.record['pid']) != self.record['identity'] or not owns_listeners(self.record['pid'], {self.config['qmp_port']}):
            return
        client = Qmp(self.config['qmp_port'])
        try:
            text = self.screen_text(client)
            if self.phase == 'waiting-recovery' and ('disk utility' in text or 'restore from time machine' in text):
                press_keys(client, ['shift', 'meta_l', 't'])
                self.phase = 'waiting-terminal'
                write_record(self.marker, {'phase': self.phase})
            elif self.phase == 'waiting-terminal' and terminal_ready(text):
                # Record the handoff before sending a potentially destructive
                # installer command. A crash requires inspection, never a blind retry.
                write_record(self.marker, {'phase': 'installer-started'})
                self.phase = 'installer-started'
                for keys in text_keys('sh /Volumes/GUESTSEED/macos-install.sh\n'):
                    press_keys(client, keys)
                print('macOS Recovery handed off to unattended startosinstall.', flush=True)
        finally:
            client.close()
