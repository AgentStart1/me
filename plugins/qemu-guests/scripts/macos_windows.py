"""Read stable Finder window numbers without Apple Events or UI permissions."""
import json
import math
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[1] / 'templates/guests/finder-windows.js.tpl').read_bytes()


def inventory(shell):
    values = json.loads(shell('/usr/bin/osascript -l JavaScript -', data=SCRIPT, timeout=20))
    if not isinstance(values, list):
        raise ValueError('Finder window inventory is invalid')
    result = {}
    for window in values:
        if not isinstance(window, dict) or set(window) != {'number', 'x', 'y', 'width', 'height'}:
            raise ValueError('Finder window inventory is invalid')
        number = window['number']
        if type(number) is not int or number <= 0 or number in result:
            raise ValueError('Finder window number is invalid or duplicated')
        rect = {key: window[key] for key in ('x', 'y', 'width', 'height')}
        if (any(type(value) not in (int, float) or not math.isfinite(value) for value in rect.values()) or
                rect['width'] <= 0 or rect['height'] <= 0):
            raise ValueError('Finder window geometry is invalid')
        result[number] = rect
    return result


def element_for_window(session, number, windows):
    rect = windows[number]
    candidates = []
    for window in session.execute('macos: listWindows', {}):
        if all(abs(float(window['rect'][key]) - rect[key]) <= 1 for key in rect):
            candidates.append(window)
    if len(candidates) != 1:
        raise RuntimeError('Owned Finder window cannot be matched unambiguously')
    identifier = candidates[0]['windowId']
    if not isinstance(identifier, str) or not identifier:
        raise ValueError('Owned Finder window has no native identifier')
    return identifier
