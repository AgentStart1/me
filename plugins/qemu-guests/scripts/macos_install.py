"""Unattended Intel Recovery terminal handoff; no setup-assistant clicking."""
import json
from pathlib import Path
import subprocess
import tempfile
import time

from guest_screen import Qmp
from process_identity import identity, owns_listeners, write_record


def key_events(keys):
    return [{'type': 'key', 'data': {'down': down, 'key': {'type': 'qcode', 'data': key}}}
            for down in (True, False) for key in (keys if down else list(reversed(keys)))]


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
        self.phase = json.loads(self.marker.read_text())['phase'] if self.marker.exists() else 'waiting-recovery'
        self.next_probe = 0

    def screen_text(self, client):
        with tempfile.TemporaryDirectory(prefix='recovery-', dir=self.home) as directory:
            image = Path(directory) / 'screen.png'
            client.execute('screendump', {'filename': str(image), 'format': 'png'})
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
                client.execute('input-send-event', {'events': key_events(['shift', 'meta_l', 't'])})
                self.phase = 'waiting-terminal'
            elif self.phase == 'waiting-terminal' and ('bash-' in text or 'zsh' in text or 'terminal' in text):
                # Record the handoff before sending a potentially destructive
                # installer command. A crash requires inspection, never a blind retry.
                write_record(self.marker, {'phase': 'installer-started'})
                self.phase = 'installer-started'
                for keys in text_keys('sh /Volumes/GUESTSEED/macos-install.sh\n'):
                    client.execute('input-send-event', {'events': key_events(keys)})
                print('macOS Recovery handed off to unattended startosinstall.', flush=True)
        finally:
            client.close()
