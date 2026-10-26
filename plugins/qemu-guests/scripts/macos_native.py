"""Owned Mac2 sessions and native UI qualification using an already built WDA."""
from contextlib import contextmanager
import json
from pathlib import Path
import re
import secrets
import time
import urllib.error
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

from test_environment_owner import CleanupUncertain
from macos_windows import element_for_window


def visible(node):
    return float(node.get('width', '0')) > 0 and float(node.get('height', '0')) > 0


def matches(root, **attributes):
    return [node for node in root.iter() if visible(node)
            and all(node.get(key) == value for key, value in attributes.items())]


def unique(nodes):
    if len(nodes) != 1:
        raise RuntimeError('Native UI target is missing or ambiguous')
    return nodes[0]


class NativeError(RuntimeError):
    def __init__(self, message):
        self.accessibility_required = 'requires the Accessibility API' in message
        self.source_unavailable = "Cannot get 'xml' source of the current application" in message
        super().__init__('Native Mac2 command failed; inspect private native-error.json')


@contextmanager
def owned_cleanup(owner, cleanup):
    """Preserve an accepted failure/cancellation while recording sticky cleanup failure."""
    primary = None
    try:
        yield
    except BaseException as error:
        primary = error
        owner.cancellation.observe(error)
        raise
    finally:
        try:
            with owner.cancellation.shield():
                owner.cleanup(cleanup)
        except BaseException as error:
            if primary is not None:
                raise primary from error
            raise


class NativeClient:
    def __init__(self, url, wda_url, owner, output, window_inventory=None):
        self.url, self.wda_url = url, wda_url
        self.owner, self.output = owner, Path(output)
        self.window_inventory = window_inventory
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def wait_ready(self):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                if self.request('GET', '/status').get('ready'):
                    return
            except (OSError, ValueError, NativeError):
                pass
            time.sleep(.5)
        raise TimeoutError('Appium server did not become ready')

    def request(self, method, path, body=None):
        self.owner.checkpoint()
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.url + path, data=data, method=method,
                                         headers={'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=120) as response:
                return json.load(response)['value']
        except urllib.error.HTTPError as error:
            payload = error.read()
            (self.output / 'native-error.json').write_bytes(payload)
            try:
                message = json.loads(payload)['value']['message']
            except (KeyError, TypeError, ValueError):
                message = ''
            raise NativeError(message) from None

    @contextmanager
    def session(self, bundle):
        # A lost or malformed creation result cannot prove that no session exists.
        try:
            result = self.request('POST', '/session', {'capabilities': {'alwaysMatch': {
                'platformName': 'mac', 'appium:automationName': 'Mac2',
                'appium:bundleId': bundle, 'appium:noReset': True,
                'appium:webDriverAgentMacUrl': self.wda_url,
                'appium:newCommandTimeout': 300}}})
            identifier = result['sessionId']
            if not isinstance(identifier, str) or not re.fullmatch('[A-Za-z0-9-]{1,128}', identifier):
                raise ValueError('Invalid session identity')
        except BaseException:
            self.owner.retain()
            raise
        session = NativeSession(self, '/session/' + identifier)
        def delete():
            try:
                self.request('DELETE', session.prefix)
            except BaseException as error:
                raise CleanupUncertain('Native session deletion is unconfirmed') from error
        with owned_cleanup(self.owner, delete):
            yield session


class NativeSession:
    def __init__(self, client, prefix):
        self.client, self.prefix = client, prefix

    def source(self):
        value = self.client.request('GET', self.prefix + '/source')
        return ET.fromstring(value)

    def source_if_ready(self):
        try:
            return self.source()
        except NativeError as error:
            if error.source_unavailable:
                return None
            raise

    def ready_source(self):
        return self.wait(lambda tree: (tree,))[0]

    def execute(self, script, arguments):
        return self.client.request('POST', self.prefix + '/execute/sync',
                                   {'script': script, 'args': [arguments]})

    def keys(self, keys):
        return self.execute('macos: keys', {'keys': keys})

    def window_ids(self):
        values = self.client.request('POST', self.prefix + '/elements',
                                     {'using': 'class name', 'value': 'XCUIElementTypeWindow'})
        return {element_id(value) for value in values}

    def close_window(self, identifier):
        if identifier not in self.window_ids():
            return
        self.keys(['XCUIKeyboardKeyEscape'])
        self.click_close(identifier)
        self.wait(lambda _tree: identifier not in self.window_ids())

    def click_close(self, identifier):
        parent = self.prefix + '/element/' + urllib.parse.quote(identifier, safe='')
        button = self.client.request('POST', parent + '/element', {
            'using': '-ios predicate string', 'value': "identifier == '_XCUI:CloseWindow'"})
        self.client.request('POST', self.prefix + '/element/' +
                            urllib.parse.quote(element_id(button), safe='') + '/click', {})

    def close_owned_window(self, number, inventory):
        self.keys(['XCUIKeyboardKeyEscape'])
        windows = inventory()
        if number not in windows:
            return
        identifier = element_for_window(self, number, windows)
        self.click_close(identifier)
        self.wait(lambda _tree: number not in inventory())

    def has_window_size(self, identifier, width, height):
        rect = self.client.request('GET', self.prefix + '/element/' +
                                   urllib.parse.quote(identifier, safe='') + '/rect')
        return rect.get('width') == width and rect.get('height') == height

    def wait(self, predicate, timeout=30):
        deadline = time.monotonic() + timeout
        tree = None
        while time.monotonic() < deadline:
            self.client.owner.checkpoint()
            tree = self.source_if_ready()
            if tree is None:
                time.sleep(.25)
                continue
            result = predicate(tree)
            if result:
                return result
            time.sleep(.25)
        if tree is not None:
            self.save_diagnostic(tree, 'native-timeout.xml')
        raise TimeoutError('Native UI condition did not become ready')

    def save_diagnostic(self, tree, name):
        for node in tree.iter('XCUIElementTypeSecureTextField'):
            node.set('value', '[REDACTED]')
        ET.ElementTree(tree).write(self.client.output / name, encoding='utf-8')


def element_id(value):
    identifier = value.get('element-6066-11e4-a52e-4f735466cecf', value.get('ELEMENT'))
    if not isinstance(identifier, str) or not identifier:
        raise ValueError('Missing native element identity')
    return identifier


def qualify(client, user, output):
    """Exercise an owned Finder window; no test source or guest compilation."""
    inventory = client.window_inventory
    if inventory is None:
        raise ValueError('Stable Finder window inventory is required for qualification')
    with client.session('com.apple.finder') as session:
        session.ready_source()
        before = inventory()
        receipt = Path(output, 'native-window-ownership.json')
        receipt.write_text(json.dumps({'phase': 'creating', 'before': before}), encoding='utf-8')
        try:
            session.keys([{'key': 'n', 'modifierFlags': 16}])
            created = session.wait(lambda _tree: set(inventory()) - set(before))
            receipt.write_text(json.dumps({'phase': 'created', 'before': before,
                                           'created': sorted(created)}), encoding='utf-8')
            number = unique(list(created))
        except BaseException:
            client.owner.retain()
            raise
        with owned_cleanup(client.owner, lambda: session.close_owned_window(number, inventory)):
            window = element_for_window(session, number, inventory())
            session.keys([{'key': 'g', 'modifierFlags': 18}])
            session.wait(lambda tree: any(visible(n) and 'go to' in (n.get('label', '') + n.get('title', '') + n.get('value', '')).lower()
                                          for n in tree.iter()))
            marker = '/Users/' + user + '/.qemu-native-input-' + secrets.token_hex(4)
            session.keys([{'key': 'a', 'modifierFlags': 16}, 'XCUIKeyboardKeyDelete', *marker])
            session.wait(lambda tree: any(n.tag in {'XCUIElementTypeTextField', 'XCUIElementTypeComboBox'}
                                          and n.get('value') == marker and visible(n) for n in tree.iter()))
            session.keys(['XCUIKeyboardKeyEscape'])
            sizes = []
            for width, height in [(640, 480), (800, 600)]:
                session.execute('macos: adjustWindow', {'windowId': window, 'width': width, 'height': height})
                session.wait(lambda _tree: session.has_window_size(window, width, height) and
                             inventory().get(number, {}).get('width') == width and
                             inventory().get(number, {}).get('height') == height)
                sizes.append([width, height])
            import base64
            frame = base64.b64decode(client.request('GET', session.prefix + '/screenshot'), validate=True)
            if not frame.startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError('Native screenshot is not PNG')
            Path(output, 'native-finder.png').write_bytes(frame)
            result = {'input_readback': True, 'window_sizes': sizes, 'native_screenshot': True}
        after = inventory()
        if any(after.get(number) != rect for number, rect in before.items()):
            raise CleanupUncertain('A pre-existing Finder window changed during qualification')
        receipt.write_text(json.dumps({'phase': 'closed', 'before': before, 'created': [number],
                                       'after': after}), encoding='utf-8')
        return result
