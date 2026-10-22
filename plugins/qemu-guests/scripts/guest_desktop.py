"""Validate optional runtime-only desktop setup, independent of consuming projects."""
import re


def validate(value, system, graphical):
    if not isinstance(value, dict) or set(value) - {'width', 'height', 'packages'}:
        raise ValueError('desktop accepts width, height and optional runtime packages')
    if system not in {'ubuntu', 'windows'} or not graphical:
        raise ValueError('desktop setup requires a graphical Ubuntu or Windows guest')
    result = {}
    for name, default, low, high in [('width', 1920, 800, 4096), ('height', 1080, 600, 4096)]:
        number = value.get(name, default)
        if type(number) is not int or not low <= number <= high:
            raise ValueError(f'desktop.{name} must be an integer in {low}..{high}')
        result[name] = number
    packages = value.get('packages', [])
    if not isinstance(packages, list) or any(not isinstance(p, str) or not re.fullmatch(r'[a-z0-9][a-z0-9+.-]*', p) for p in packages):
        raise ValueError('desktop.packages must contain runtime package names')
    if system == 'windows' and packages:
        raise ValueError('Windows desktop dependencies must be provided as prebuilt runtime artifacts')
    result['packages'] = packages
    return result


LINUX_PACKAGES = ['xvfb', 'openbox', 'x11-utils', 'dbus-x11', 'libsecret-tools', 'gnome-keyring',
                  'python3-pyatspi', 'python3-gi', 'gir1.2-gtk-3.0', 'xdotool', 'libglib2.0-bin']
