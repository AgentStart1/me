"""Re-register explicitly approved applications through System Settings only."""
import time

from macos_native import matches, unique, visible, owned_cleanup
from macos_console import authorization_prompt


class PermissionRepair:
    def __init__(self, native, console, shell, password, *, authorization_identity):
        self.native, self.console, self.shell, self.password = native, console, shell, password
        self.authorization_identity = authorization_identity

    def authenticate(self, secure):
        field = unique(secure) if secure else self.console.authorization_field()
        self.console.click(field)
        # Clicking a label is not evidence of password focus. The OS must report
        # secure input owned by a reviewed system authorization executable.
        target = self.authorization_identity()
        if not self.console.is_authorization() or self.authorization_identity() != target:
            raise RuntimeError('System authorization target changed before credential entry')
        self.console.text(self.password)
        self.console.press('ret')

    def wait(self, session, predicate, timeout=120):
        deadline = time.monotonic() + timeout
        authenticated = False
        next_auth_probe = 0
        tree = None
        while time.monotonic() < deadline:
            tree = session.source_if_ready()
            result = predicate(tree) if tree is not None else None
            if result:
                return result
            if not authenticated and time.monotonic() >= next_auth_probe:
                nodes = list(tree.iter()) if tree is not None else []
                secure = [n for n in nodes if n.tag == 'XCUIElementTypeSecureTextField' and visible(n)]
                words = ' '.join(n.get(key, '') for n in nodes if visible(n)
                                 for key in ('label', 'title', 'value')
                                 if n.tag != 'XCUIElementTypeSecureTextField')
                if authorization_prompt(words) or self.console.is_authorization():
                    self.authenticate(secure)
                    authenticated = True  # Never guess or repeatedly submit a credential.
                next_auth_probe = time.monotonic() + 3
            time.sleep(.3)
        if tree is not None:
            session.save_diagnostic(tree, 'permission-timeout.xml')
        raise TimeoutError('System Settings permission transition did not complete')

    def repair(self, targets, reregister=False):
        with self.native.session('com.apple.systempreferences') as session:
            self.shell('open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"')
            self.wait(session, lambda tree: matches(tree, label='Add'))
            for target in targets:
                self.repair_target(session, target, reregister)

    def repair_target(self, session, target, reregister=False):
        identifier = target.name + '_Title'
        tree = session.ready_source()
        existing = matches(tree, identifier=identifier)
        if existing and not reregister:
            toggle = unique(matches(tree, identifier=target.name + '_Toggle'))
            if toggle.get('value') != '1':
                self.console.click(toggle)
                self.wait(session, lambda tree: matches(tree, identifier=target.name + '_Toggle', value='1'))
            return
        if existing:
            self.console.click(unique(existing))
            remove = self.wait(session, lambda tree: matches(tree, label='Remove', enabled='true'))
            self.console.click(unique(remove))
            self.wait(session, lambda tree: not matches(tree, identifier=identifier))
        with owned_cleanup(self.native.owner, lambda: session.keys(['XCUIKeyboardKeyEscape', 'XCUIKeyboardKeyEscape'])):
            self.add_target(session, target)

    def add_target(self, session, target):
        self.console.click(unique(matches(session.ready_source(), label='Add', enabled='true')))
        # The file picker is allowed to appear only after any authorization has completed.
        self.wait(session, lambda tree: matches(tree, identifier='OKButton'))
        self.console.press('meta_l', 'shift', 'g')
        self.wait(session, lambda tree: any('go to' in (n.get('label', '') + n.get('title', '') + n.get('value', '')).lower()
                                          and visible(n) for n in tree.iter()))
        self.console.press('meta_l', 'a')
        self.console.text(target.path)
        self.wait(session, lambda tree: any(n.get('value') == target.path and visible(n) for n in tree.iter()))
        self.console.press('ret')
        opened = self.wait(session, lambda tree: matches(tree, identifier='OKButton', enabled='true'))
        self.console.click(unique(opened))
        toggle = self.wait(session, lambda tree: matches(tree, identifier=target.name + '_Toggle'))
        if unique(toggle).get('value') != '1':
            self.console.click(unique(toggle))
        self.wait(session, lambda tree: matches(tree, identifier=target.name + '_Toggle', value='1'))
