"""Physical guest input and narrowly recognized macOS authorization prompts."""
from pathlib import Path
import csv
import io
import subprocess
import time
import re

from guest_screen import Qmp


SHIFTED = dict(zip('!@#$%^&*()', '1234567890'))
SHIFTED.update({'_': 'minus', '+': 'equal', ':': 'semicolon', '"': 'apostrophe', '?': 'slash',
                '<': 'comma', '>': 'dot', '{': 'bracket_left', '}': 'bracket_right',
                '|': 'backslash', '~': 'grave_accent'})
PLAIN = dict(zip('-=;\'/,.[]\\` ', ['minus', 'equal', 'semicolon', 'apostrophe', 'slash',
                 'comma', 'dot', 'bracket_left', 'bracket_right', 'backslash', 'grave_accent', 'spc']))


def text_keys(value):
    result = []
    for char in value:
        if not char.isascii() or not (char.isalnum() or char in SHIFTED or char in PLAIN):
            raise ValueError('Guest keyboard input requires the configured ASCII layout')
        result.append((['shift'] if char.isupper() or char in SHIFTED else []) +
                      [SHIFTED.get(char, PLAIN.get(char, char.lower()))])
    return result


def authorization_prompt(text):
    normalized = re.sub('[^a-z]', '', text.lower())
    return ('privacysecurity' in normalized and 'enteryourpasswordtoallowthis' in normalized
            and 'modifysettings' in normalized)


def normalized_caption(value):
    return re.sub(r'\W', '', value.casefold())


def ocr_lines(rows):
    groups = {}
    for row in rows:
        if row['text'].strip():
            key = tuple(row[name] for name in ('block_num', 'par_num', 'line_num'))
            groups.setdefault(key, []).append(row)
    return list(groups.values())


def ocr_rows(text):
    # Tesseract TSV does not quote/escape recognized quote characters as CSV.
    return list(csv.DictReader(io.StringIO(text), delimiter='\t', quoting=csv.QUOTE_NONE))


def account_labels(rows, name):
    matches = []
    for line in ocr_lines(rows):
        for start in range(len(line)):
            for end in range(start + 1, len(line) + 1):
                words = line[start:end]
                if (normalized_caption(' '.join(row['text'] for row in words)) == normalized_caption(name)
                        and all(float(row['conf']) >= 60 for row in words)):
                    matches.append(words)
    return matches


def positioned_rows(rows, box, scale, prefix):
    for row in rows:
        row['left'] = str(round(int(row['left']) * 2 / scale + box[0] * 2))
        row['top'] = str(round(int(row['top']) * 2 / scale + box[1] * 2))
        row['width'] = str(round(int(row['width']) * 2 / scale))
        row['height'] = str(round(int(row['height']) * 2 / scale))
        row['block_num'] = prefix + row['block_num']
    return rows


def login_password_field(rows, account_label):
    if not account_label or normalized_caption(account_label) not in normalized_caption(' '.join(row['text'] for row in rows)):
        raise ValueError('Locked console account label is not visible')
    # The insertion caret lowers the first word's OCR confidence. Require the
    # exact complete caption, a confident average and no very weak word.
    candidates = [group for group in ocr_lines(rows)
                  if normalized_caption(' '.join(row['text'] for row in group)) == 'enterpassword'
                  and min(float(row['conf']) for row in group) >= 40
                  and sum(float(row['conf']) for row in group) / len(group) >= 70]
    if len(candidates) != 1:
        raise ValueError('System login password field is missing or ambiguous')
    return field_bounds(candidates[0])


def field_bounds(words):
    left, top = min(int(row['left']) for row in words), min(int(row['top']) for row in words)
    right = max(int(row['left']) + int(row['width']) for row in words)
    bottom = max(int(row['top']) + int(row['height']) for row in words)
    return {'enabled': 'true', 'x': str(left / 2), 'y': str(top / 2),
            'width': str((right - left) / 2), 'height': str((bottom - top) / 2)}


def authorization_password_field(rows, field_rows=None):
    if not authorization_prompt(' '.join(row['text'] for row in rows)):
        raise ValueError('System authorization prompt is not visible')
    candidates = [group for group in ocr_lines(rows if field_rows is None else field_rows)
                  if normalized_caption(' '.join(row['text'] for row in group)) in {'password', 'enterpassword'}
                  and all(float(row['conf']) >= 60 for row in group)]
    if len(candidates) != 1:
        raise ValueError('System authorization password field is missing or ambiguous')
    return field_bounds(candidates[0])


class MacConsole:
    def __init__(self, port, output, tesseract, owner):
        self.qmp = Qmp(port)
        self.output, self.tesseract, self.owner = Path(output), tesseract, owner
        self.qmp.socket.settimeout(15)
        try:
            self.frame = self.capture()
            from PIL import Image
            with Image.open(self.frame) as image:
                self.width, self.height = image.size
        except BaseException:
            self.qmp.close()
            raise

    def close(self):
        self.qmp.close()

    def capture(self):
        path = self.output / 'console.png'
        self.qmp.execute('screendump', {'filename': str(path), 'format': 'png'})
        return path

    def press(self, *keys):
        self.owner.checkpoint()
        self.qmp.execute('send-key', {'keys': [{'type': 'qcode', 'data': k} for k in keys], 'hold-time': 35})
        time.sleep(.09)

    def text(self, value):
        for keys in text_keys(value):
            self.press(*keys)

    def click(self, node):
        if node.get('enabled') != 'true':
            raise ValueError('Native UI target is disabled')
        x = float(node.get('x')) + float(node.get('width')) / 2
        y = float(node.get('y')) + float(node.get('height')) / 2
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError('Native UI coordinates do not match the guest framebuffer')
        self.owner.checkpoint()
        self.qmp.execute('input-send-event', {'events': [
            {'type': 'abs', 'data': {'axis': 'x', 'value': round(x * 32767 / (self.width - 1))}},
            {'type': 'abs', 'data': {'axis': 'y', 'value': round(y * 32767 / (self.height - 1))}}]})
        time.sleep(.1)
        try:
            self.qmp.execute('input-send-event', {'events': [{'type': 'btn', 'data': {'button': 'left', 'down': True}}]})
            time.sleep(.1)
        finally:
            self.qmp.execute('input-send-event', {'events': [{'type': 'btn', 'data': {'button': 'left', 'down': False}}]})

    def ocr(self, tsv=False, box=None, scale=2, mode='11', frame=None):
        path = self.capture() if frame is None else frame
        from PIL import Image, ImageOps
        enlarged = self.output / 'authorization-ocr.png'
        with Image.open(path) as frame:
            if box is not None:
                frame = ImageOps.autocontrast(frame.crop(box).convert('L'))
            frame.resize((frame.width * scale, frame.height * scale)).save(enlarged)
        result = subprocess.run([self.tesseract, str(enlarged), 'stdout', '--psm', mode,
                                 *(['tsv'] if tsv else [])],
                                capture_output=True, check=True, timeout=15)
        return result.stdout.decode(errors='replace')

    def is_authorization(self):
        try:
            self.authorization_field()
            return True
        except ValueError:
            return False

    def authorization_field(self):
        if (self.width, self.height) != (1920, 1080):
            raise ValueError('Authorization recognition is qualified only for the 1920x1080 Sequoia console')
        frame = self.capture()
        x, y = self.width // 2, self.height // 2
        # The disabled button and placeholder need separate contrast ranges.
        # Crops constrain recognition; clicks still use the recognized caption,
        # followed by verification of the OS secure-input owner.
        def rows(box, scale, mode, prefix):
            return positioned_rows(ocr_rows(self.ocr(tsv=True, box=box, scale=scale,
                                                     mode=mode, frame=frame)), box, scale, prefix)
        prompt = rows((x - 180, y - 240, x + 180, y + 200), 3, '11', 'dialog-')
        button = rows((x - 110, y + 83, x + 110, y + 101), 4, '7', 'button-')
        field = rows((x - 110, y + 35, x + 110, y + 54), 4, '7', 'password-')
        return authorization_password_field(prompt + button, field)

    def unlock(self, account_label, password, confirm_target):
        # The caller must first verify the locked on-console account and the
        # system loginwindow secure-input process. Submit only once, never guess.
        if (self.width, self.height) != (1920, 1080):
            raise ValueError('Automatic login is qualified only for the 1920x1080 Sequoia console')
        self.press('shift')  # Wake the verified login UI without entering text.
        time.sleep(.5)
        panel = (self.width // 2 - 60, self.height - 148,
                 self.width // 2 + 60, self.height - 122)
        rows = positioned_rows(ocr_rows(self.ocr(tsv=True, box=panel, scale=4, mode='7')),
                               panel, 4, 'account-')
        labels = account_labels(rows, account_label)
        if len(labels) != 1:
            raise ValueError('Locked console account label is missing or ambiguous')
        label = labels[0]
        left = min(int(row['left']) for row in label)
        right = max(int(row['left']) + int(row['width']) for row in label)
        bottom = max(int(row['top']) + int(row['height']) for row in label) / 2
        unit = max(.5, round(max(int(row['height']) for row in label) / 16) / 2)
        center = (left + right) / 4
        # The qualified Sequoia login layout puts the low-contrast placeholder
        # below the account label. Crop only for recognition, never blind input.
        box = tuple(round(value) for value in (center - 70 * unit, bottom + 20 * unit,
                                                center + 70 * unit, bottom + 42 * unit))
        field = positioned_rows(ocr_rows(self.ocr(tsv=True, box=box, scale=4, mode='7')),
                                box, 4, 'field-')
        self.click(login_password_field([*label, *field], account_label))
        confirm_target()
        self.text(password)
        self.press('ret')
