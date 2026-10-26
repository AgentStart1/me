"""Prepared macOS identities, physical input and session ownership contracts."""
import importlib.util
from contextlib import nullcontext, redirect_stdout
import io
import json
import signal
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch
import xml.etree.ElementTree as ET
import zipfile

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from macos_console import (MacConsole, authorization_prompt, authorization_password_field,
                           login_password_field, ocr_rows, text_keys)
from macos_desktop_plan import load
from macos_native import NativeClient, NativeError, NativeSession, matches, unique, qualify
from macos_permissions import PermissionRepair
from test_environment_owner import CleanupUncertain
from resource_ownership import Cancelled
from test_cancellation import CancellationRequest, cancellation_context, current_cancellation
from test_environment_owner import OwnerState, TestEnvironmentOwner
from macos_wda import restart as restart_wda, stop_runner
from macos_windows import inventory as window_inventory, element_for_window


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        with zipfile.ZipFile(self.home / 'private.zip', 'w') as archive:
            archive.writestr('account-password', 'synthetic-secret_123')
        self.data = {'expected_build': '24A123', 'wda_url': 'http://127.0.0.1:10100',
                     'wda_service': 'com.example.prebuilt-wda', 'password_archive': 'private.zip',
                     'permissions': [{'name': 'Test Runner', 'path': '/Applications/Test Runner.app',
                                      'bundle_id': 'com.example.runner', 'cdhash': 'a' * 40}]}

    def plan(self):
        path = self.home / 'plan.json'
        path.write_text(json.dumps(self.data))
        return load(path)

    def test_credential_is_not_in_plan_representation(self):
        plan = self.plan()
        self.assertNotIn('synthetic-secret', repr(plan))
        self.assertEqual(plan.password, 'synthetic-secret_123')

    def test_remote_wda_is_rejected_before_any_native_session(self):
        self.data['wda_url'] = 'http://example.invalid:10100'
        with self.assertRaisesRegex(ValueError, 'loopback'):
            self.plan()

    def test_unreviewed_application_identity_is_rejected(self):
        self.data['permissions'][0]['cdhash'] = 'latest'
        with self.assertRaisesRegex(ValueError, 'identity'):
            self.plan()

    def test_parent_traversal_is_rejected(self):
        self.data['permissions'][0]['path'] = '/Applications/../Other.app'
        with self.assertRaisesRegex(ValueError, 'absolute'):
            self.plan()

    def test_duplicate_ui_names_are_rejected(self):
        self.data['permissions'] *= 2
        with self.assertRaisesRegex(ValueError, 'unique'):
            self.plan()

    def test_unknown_fields_are_not_ignored(self):
        self.data['disable_security'] = True
        with self.assertRaisesRegex(ValueError, 'fields'):
            self.plan()

    def test_artifact_name_cannot_escape_staging_directory(self):
        self.data['files'] = [{'source': 'private.zip', 'name': '../other', 'sha256': 'a' * 64}]
        with self.assertRaisesRegex(ValueError, 'basename'):
            self.plan()

    def test_setup_bytes_are_captured_and_change_the_fingerprint(self):
        script = self.home / 'setup.sh'
        script.write_bytes(b'#!/bin/sh\ntrue\n')
        self.data['setup_script'] = 'setup.sh'
        first = self.plan()
        script.write_bytes(b'#!/bin/sh\nfalse\n')
        second = self.plan()
        self.assertNotEqual(first.digest, second.digest)
        self.assertEqual(first.setup_script, b'#!/bin/sh\ntrue\n')

    def test_credential_rotation_invalidates_preparation(self):
        first = self.plan()
        with zipfile.ZipFile(self.home / 'private.zip', 'w') as archive:
            archive.writestr('account-password', 'rotated-synthetic-secret')
        self.assertNotEqual(first.digest, self.plan().digest)

    def test_manifest_collections_require_arrays(self):
        for name in ('permissions', 'files', 'checks'):
            with self.subTest(name=name):
                original = self.data.get(name, [])
                self.data[name] = None
                with self.assertRaisesRegex(ValueError, 'arrays'):
                    self.plan()
                self.data[name] = original


class InputTests(unittest.TestCase):
    def test_ocr_quote_characters_do_not_consume_later_rows(self):
        self.assertEqual([row['text'] for row in ocr_rows('level\ttext\n5\t"\n5\tDeveloper\n')],
                         ['"', 'Developer'])
    def login_rows(self):
        return [{'text': word, 'block_num': block, 'par_num': '1', 'line_num': '1',
                 'conf': '95', 'left': str(left), 'top': '200', 'width': '40', 'height': '20'}
                for word, block, left in [('Test', '1', 0), ('Enter', '2', 100), ('Password', '2', 150)]]

    def test_login_field_requires_matching_account_and_unambiguous_caption(self):
        rows = self.login_rows()
        self.assertEqual(login_password_field(rows, 'Test')['x'], '50.0')
        with self.assertRaisesRegex(ValueError, 'account label'):
            login_password_field(rows, 'Other')
        duplicate = [{**row, 'block_num': '3'} for row in rows if row['block_num'] == '2']
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            login_password_field(rows + duplicate, 'Test')

    def test_changed_login_target_never_receives_a_credential(self):
        import csv
        output = io.StringIO()
        rows = self.login_rows()
        writer = csv.DictWriter(output, fieldnames=list(rows[0]), delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)
        console = object.__new__(MacConsole)
        console.width, console.height = 1920, 1080
        console.ocr = Mock(return_value=output.getvalue())
        console.click, console.text, console.press = Mock(), Mock(), Mock()
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            console.unlock('Test', 'synthetic-secret', Mock(side_effect=RuntimeError('target changed')))
        console.text.assert_not_called()
        self.assertFalse(any(call.args == ('ret',) for call in console.press.call_args_list))

    def test_generated_password_punctuation_has_explicit_keyboard_mapping(self):
        self.assertEqual(text_keys('A_!'), [['shift', 'a'], ['shift', 'minus'], ['shift', '1']])

    def test_unsupported_keyboard_layout_fails_before_typing(self):
        with self.assertRaises(ValueError):
            text_keys('example\npassword')

    def test_only_the_system_permission_authentication_prompt_matches(self):
        self.assertTrue(authorization_prompt('Privacy & Security\nEnter your password to allow this.\nModify Settings'))
        self.assertFalse(authorization_prompt('Website privacy & security: enter your password'))
        self.assertFalse(authorization_prompt('Privacy & Security\nModify Settings'))

    def test_authorization_requires_a_distinct_unambiguous_password_caption(self):
        rows = [{'text': text, 'block_num': str(i), 'par_num': '1', 'line_num': '1',
                 'conf': '95', 'left': '100', 'top': '200', 'width': '80', 'height': '20'}
                for i, text in enumerate(['Privacy & Security', 'Enter your password to allow this',
                                           'Modify Settings', 'Password'])]
        self.assertEqual(authorization_password_field(rows)['x'], '50.0')
        with self.assertRaisesRegex(ValueError, 'missing or ambiguous'):
            authorization_password_field(rows[:-1])
        with self.assertRaisesRegex(ValueError, 'missing or ambiguous'):
            authorization_password_field(rows + [{**rows[-1], 'block_num': 'other'}])

    def test_hidden_menu_entries_are_not_physical_click_targets(self):
        tree = ET.fromstring('<root><button label="Add" width="0" height="0"/>'
                             '<button label="Add" width="12" height="12"/></root>')
        self.assertEqual(len(matches(tree, label='Add')), 1)

    def test_ambiguous_target_never_selects_the_first_match(self):
        with self.assertRaisesRegex(RuntimeError, 'ambiguous'):
            unique([object(), object()])


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.owner = Mock()
        self.owner.cancellation.shield = nullcontext
        def cleanup(function, *args):
            try:
                return function(*args)
            except BaseException:
                self.owner.retain()
                raise
        self.owner.cleanup.side_effect = cleanup
        self.client = NativeClient('http://127.0.0.1:1234', 'http://127.0.0.1:10100',
                                   self.owner, self.temporary.name)

    def test_malformed_creation_retains_ownership_without_bulk_cleanup(self):
        self.client.request = Mock(return_value={})
        with self.assertRaises(KeyError):
            with self.client.session('com.example.runner'):
                self.fail('No session identity was returned')
        self.owner.retain.assert_called_once()
        self.assertEqual(self.client.request.call_count, 1)

    def test_only_the_created_session_is_deleted(self):
        self.client.request = Mock(side_effect=[{'sessionId': 'specific-session'}, None])
        with self.client.session('com.example.runner'):
            pass
        self.assertEqual(self.client.request.call_args.args, ('DELETE', '/session/specific-session'))
        self.owner.retain.assert_not_called()

    def test_unconfirmed_deletion_retains_the_guest(self):
        self.client.request = Mock(side_effect=[{'sessionId': 'specific-session'}, TimeoutError()])
        with self.assertRaises(CleanupUncertain):
            with self.client.session('com.example.runner'):
                pass
        self.owner.retain.assert_called_once()

    def test_cancellation_identity_survives_failed_deletion(self):
        original = Cancelled(2)
        self.client.request = Mock(side_effect=[{'sessionId': 'specific-session'}, TimeoutError()])
        with self.assertRaises(Cancelled) as raised:
            with self.client.session('com.example.runner'):
                raise original
        self.assertIs(raised.exception, original)
        self.assertIsInstance(original.__cause__, CleanupUncertain)
        self.owner.retain.assert_called_once()


class WindowCleanupTests(unittest.TestCase):
    def test_only_the_known_unavailable_snapshot_is_waited_for(self):
        client = Mock()
        session = NativeSession(client, '/session/test')
        session.source = Mock(side_effect=[NativeError("Cannot get 'xml' source of the current application"),
                                           ET.fromstring('<application/>')])
        with patch('macos_native.time.sleep'):
            self.assertTrue(session.wait(lambda tree: True))
        self.assertEqual(session.source.call_count, 2)

    def test_other_native_errors_are_not_hidden_by_snapshot_waiting(self):
        session = NativeSession(Mock(), '/session/test')
        session.source = Mock(side_effect=NativeError('Different native failure'))
        with self.assertRaises(NativeError):
            session.wait(lambda tree: True)
        session.source.assert_called_once()

    def test_an_enabled_approved_grant_is_not_removed(self):
        native, console, session = Mock(), Mock(), Mock()
        session.ready_source.return_value = ET.fromstring('<root>'
            '<text identifier="Test Runner_Title" width="10" height="10"/>'
            '<toggle identifier="Test Runner_Toggle" value="1" width="10" height="10"/></root>')
        target = Mock()
        target.name = 'Test Runner'
        PermissionRepair(native, console, Mock(), 'synthetic-secret',
                         authorization_identity=Mock()).repair_target(session, target)
        self.assertEqual(console.method_calls, [])

    def test_accepted_cancellation_still_deletes_the_known_native_session(self):
        request = CancellationRequest()
        owner = TestEnvironmentOwner(cancellation=request)
        with tempfile.TemporaryDirectory() as directory:
            client = NativeClient('http://127.0.0.1:4723', 'http://127.0.0.1:10100', owner, directory)
            client.opener.open = Mock(side_effect=[
                io.BytesIO(b'{"value":{"sessionId":"known-session"}}'), io.BytesIO(b'{"value":null}')])
            with cancellation_context(request):
                with self.assertRaises(Cancelled) as raised:
                    with owner:
                        with client.session('com.example.app'):
                            request.request(signal.SIGINT)
                            owner.checkpoint()
            self.assertIs(raised.exception, request.accepted)
            self.assertIs(owner.state, OwnerState.RELEASED)
            self.assertEqual(client.opener.open.call_count, 2)
            deletion = client.opener.open.call_args.args[0]
            self.assertEqual(deletion.method, 'DELETE')
            self.assertTrue(deletion.full_url.endswith('/session/known-session'))

    def test_lost_new_window_response_retains_the_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Mock(window_inventory=Mock(return_value={}))
            session = Mock()
            session.keys.side_effect = TimeoutError('creation response lost')
            client.session.return_value = nullcontext(session)
            with self.assertRaises(TimeoutError):
                qualify(client, 'test', directory)
            client.owner.retain.assert_called_once()
            self.assertEqual(json.loads((Path(directory) / 'native-window-ownership.json').read_text())['phase'],
                             'creating')

    def test_native_identifier_changes_do_not_change_window_ownership(self):
        session = Mock()
        rect = {'x': 100, 'y': 100, 'width': 800, 'height': 600}
        session.execute.return_value = [
            {'windowId': 'changed-existing-id', 'rect': {**rect, 'x': 50}},
            {'windowId': 'changed-owned-id', 'rect': rect}]
        self.assertEqual(element_for_window(session, 42, {42: rect}), 'changed-owned-id')

    def test_inventory_rejects_duplicate_system_window_numbers(self):
        value = {'number': 42, 'x': 100, 'y': 100, 'width': 800, 'height': 600}
        with self.assertRaisesRegex(ValueError, 'duplicated'):
            window_inventory(Mock(return_value=json.dumps([value, value]).encode()))

    def test_owned_window_cleanup_confirms_system_window_disappearance(self):
        client = Mock()
        closed = False
        rect = {'x': 100, 'y': 100, 'width': 800, 'height': 600}
        seen = []

        def inventory():
            value = {28: {**rect, 'x': 50}, **({} if closed else {42: rect})}
            seen.append(set(value))
            return value

        def request(method, path, body=None):
            nonlocal closed
            if path.endswith('/execute/sync') and body['script'] == 'macos: listWindows':
                return [{'windowId': 'fresh-id', 'rect': rect}]
            if path.endswith('/element/fresh-id/element'):
                return {'ELEMENT': 'owned-close'}
            if path.endswith('/element/owned-close/click'):
                closed = True
            if path.endswith('/source'):
                return '<application/>'
            return None

        client.request.side_effect = request
        NativeSession(client, '/session/test').close_owned_window(42, inventory)
        self.assertTrue(closed)
        self.assertEqual(seen[-1], {28})

    def test_private_timeout_diagnostics_redact_secure_input(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Mock(output=Path(directory))
            tree = ET.fromstring('<root><XCUIElementTypeSecureTextField value="synthetic-secret"/></root>')
            NativeSession(client, '/session/test').save_diagnostic(tree, 'permission-timeout.xml')
            data = (Path(directory) / 'permission-timeout.xml').read_text()
            self.assertNotIn('synthetic-secret', data)
            self.assertIn('[REDACTED]', data)

    def test_only_the_owned_window_is_closed_and_its_disappearance_is_confirmed(self):
        client = Mock()
        closed = False
        window_queries = []

        def request(method, path, body=None):
            nonlocal closed
            if path.endswith('/elements'):
                windows = ['existing-window'] + ([] if closed else ['owned-window'])
                window_queries.append(windows)
                return [{'ELEMENT': value} for value in windows]
            if path.endswith('/source'):
                return '<application/>'
            if path.endswith('/element/owned-window/element'):
                return {'ELEMENT': 'owned-close-button'}
            if path.endswith('/element/owned-close-button/click'):
                closed = True
            return None

        client.request.side_effect = request
        NativeSession(client, '/session/test').close_window('owned-window')
        self.assertTrue(closed)
        self.assertGreaterEqual(len(window_queries), 2)
        self.assertEqual(window_queries[-1], ['existing-window'])
        self.assertFalse(any('/element/existing-window' in call.args[1]
                             for call in client.request.call_args_list))


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.console = Mock()
        self.identity = Mock(return_value=(123, 'reviewed system process'))
        self.repair = PermissionRepair(Mock(), self.console, Mock(), 'synthetic-secret',
                                        authorization_identity=self.identity)

    def test_ocr_prompt_without_a_password_field_never_receives_a_credential(self):
        self.console.authorization_field.side_effect = ValueError('password field missing')
        with self.assertRaisesRegex(ValueError, 'password field'):
            self.repair.authenticate([])
        self.console.text.assert_not_called()
        self.identity.assert_not_called()

    def test_unverified_secure_input_never_receives_a_credential(self):
        self.identity.side_effect = RuntimeError('unreviewed process')
        with self.assertRaisesRegex(RuntimeError, 'unreviewed'):
            self.repair.authenticate([])
        self.console.text.assert_not_called()

    def test_changed_authorization_target_never_receives_a_credential(self):
        self.identity.side_effect = [(123, 'first'), (124, 'replacement')]
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            self.repair.authenticate([])
        self.console.text.assert_not_called()

    def test_disappeared_authorization_prompt_never_receives_a_credential(self):
        self.console.is_authorization.return_value = False
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            self.repair.authenticate([])
        self.console.text.assert_not_called()

    def test_verified_ocr_field_is_focused_before_one_credential_submission(self):
        field = {'enabled': 'true', 'x': '10', 'y': '20', 'width': '30', 'height': '20'}
        self.console.authorization_field.return_value = field
        self.repair.authenticate([])
        self.console.click.assert_called_once_with(field)
        self.identity.assert_called()
        self.console.text.assert_called_once_with('synthetic-secret')
        self.console.press.assert_called_once_with('ret')


class WdaRestartTests(unittest.TestCase):
    def test_runner_exit_between_identity_check_and_term_is_confirmed(self):
        record = '427 501 timestamp /Applications/Test Runner.app/Contents/MacOS/Runner'
        shell = Mock(side_effect=[record.encode(), b'Runner', RuntimeError('already exited'), b''])
        plan = Mock(permissions=(Mock(path='/Applications/Test Runner.app'),))
        stop_runner(shell, 427, '501', plan, Mock())
        self.assertEqual(shell.call_count, 4)

    def test_a_replacement_after_failed_term_is_never_accepted_as_exit(self):
        record = '427 501 timestamp /Applications/Test Runner.app/Contents/MacOS/Runner'
        shell = Mock(side_effect=[record.encode(), b'Runner', RuntimeError('identity changed'),
                                  b'427 501 later /Applications/Other.app/Other'])
        plan = Mock(permissions=(Mock(path='/Applications/Test Runner.app'),))
        with self.assertRaises(CleanupUncertain):
            stop_runner(shell, 427, '501', plan, Mock())

    def test_reviewed_orphan_is_stopped_before_the_service_is_reloaded(self):
        owner = MagicMock()
        plan = Mock(wda_url='http://127.0.0.1:10100', wda_service='com.example.wda',
                    permissions=(Mock(path='/Applications/Test Runner.app'),))
        alive = True
        stopped = False
        loaded = False
        record = '427 501 Sun Oct 25 07:28:20 2026 /Applications/Test Runner.app/Contents/MacOS/Runner'

        def shell(command, **kwargs):
            nonlocal alive, stopped, loaded
            if command == 'id -u':
                return b'501\n'
            if command.startswith('launchctl bootout'):
                stopped = True
            elif command.startswith('/usr/sbin/lsof'):
                self.assertTrue(stopped)
                return b'427\n'
            elif command.startswith('/usr/libexec/PlistBuddy'):
                return b'Runner\n'
            elif command.startswith('actual='):
                self.assertIn(record, command)
                self.assertTrue(command.endswith('kill -TERM 427'))
                alive = False
            elif command.startswith('ps -ww'):
                return record.encode() if alive else b''
            elif command.startswith('launchctl bootstrap'):
                self.assertFalse(alive)
                loaded = True
            else:
                self.fail('Unexpected guest operation')
            return b''

        restart_wda(shell, {'ssh_user': 'test'}, plan, owner)
        self.assertTrue(loaded)
        owner.retain.assert_not_called()

    def test_an_unreviewed_listener_is_never_signaled(self):
        owner = MagicMock()
        plan = Mock(wda_url='http://127.0.0.1:10100', wda_service='com.example.wda',
                    permissions=(Mock(path='/Applications/Test Runner.app'),))
        shell = Mock(side_effect=[b'501', b'', b'427',
                                  b'427 501 Sun Oct 25 07:28:20 2026 /Applications/Other.app/Other', b'Runner'])
        with self.assertRaises(CleanupUncertain):
            restart_wda(shell, {'ssh_user': 'test'}, plan, owner)
        self.assertFalse(any('kill -TERM' in call.args[0] for call in shell.call_args_list))
        owner.retain.assert_called_once()


class ReceiptTests(unittest.TestCase):
    def test_terminal_receipts_are_published_after_cleanup_with_the_lease_held(self):
        spec = importlib.util.spec_from_file_location('macos_desktop_receipts', SCRIPTS / 'macos-desktop.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for phase in ('ready', 'failed', 'recovery-required'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                (home / 'known_hosts').touch()
                state = home / 'macos-desktop/state.json'
                owner = TestEnvironmentOwner(home)
                transport = Mock()
                failure = ValueError('qualification failed') if phase == 'failed' else OSError('cleanup failed')
                if phase == 'recovery-required':
                    transport.close.side_effect = failure
                record = {'pid': 1, 'identity': ['fixture', 1], 'token': 'fixture'}
                original_write = module.write_record
                published = []
                def publish(path, value):
                    if path == state and value['phase'] != 'checking':
                        self.assertTrue((home / 'test-environment.lock').exists())
                        self.assertTrue(transport.close.called)
                        self.assertIsNot(owner.state, OwnerState.RELEASED)
                        published.append(value['phase'])
                    original_write(path, value)
                with patch.object(module, 'verified_record', return_value=record), \
                        patch.object(module, 'GuestTransport', return_value=transport), \
                        patch.object(module, 'shell', side_effect=[b'24H32', b'x86_64']), \
                        patch.object(module, 'verify_desktop', side_effect=failure if phase == 'failed' else None,
                                     return_value={'native': True}), patch.object(module, 'write_record', side_effect=publish):
                    expected = self.assertRaises(type(failure)) if phase != 'ready' else nullcontext()
                    with expected, redirect_stdout(io.StringIO()):
                        module.run('verify', {'os': 'macos', 'graphical': True, 'state_dir': str(home)},
                                   Mock(digest='fixture', expected_build='24H32'), owner=owner)
                self.assertEqual(published, [phase])
                self.assertEqual(json.loads(state.read_text())['phase'], phase)

    def test_a_competing_reservation_cannot_overwrite_a_ready_receipt(self):
        spec = importlib.util.spec_from_file_location('macos_desktop_cli', SCRIPTS / 'macos-desktop.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / 'known_hosts').write_text('synthetic host key')
            (home / 'macos-desktop').mkdir()
            state = home / 'macos-desktop/state.json'
            original = b'{"phase":"ready","plan_sha256":"existing"}'
            state.write_bytes(original)
            owner = Mock()
            owner.__enter__ = Mock(side_effect=RuntimeError('reservation busy'))
            owner.__exit__ = Mock()
            with patch.object(module, 'TestEnvironmentOwner', return_value=owner):
                with self.assertRaises(RuntimeError):
                    module.run('verify', {'os': 'macos', 'graphical': True, 'state_dir': str(home)}, Mock())
            self.assertEqual(state.read_bytes(), original)


class PreparationTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('macos_desktop_preparation', SCRIPTS / 'macos-desktop.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.transport = Mock(target='test@127.0.0.1')
        self.file = Mock(source=Path('prepared.tar.gz'), sha256='a' * 64)
        self.file.name = 'prepared.tar.gz'
        self.plan = Mock(files=(self.file,), setup_script=b'true\n', password='synthetic-secret')
        self.config = {'ssh_user': 'test', 'state_dir': 'state', 'access_key': 'private-key', 'ssh_port': 2222}

    def test_matching_archive_is_reused_when_setup_needs_to_run_again(self):
        with patch.object(self.module, 'shell', side_effect=[b'', b'a' * 64 + b'  archive', b'', b'']) as shell:
            with redirect_stdout(io.StringIO()):
                self.module.prepare(self.transport, self.config, self.plan)
        self.transport.run.assert_not_called()
        self.assertEqual(shell.call_args.kwargs['data'], b'synthetic-secret\nsynthetic-secret\n')
        self.assertIn('/bin/bash', shell.call_args.args[1])

    def test_mismatched_archive_must_be_verified_after_retransfer(self):
        self.plan.setup_script = None
        with patch.object(self.module, 'shell', side_effect=[b'', b'b' * 64 + b'  archive', b'c' * 64 + b'  archive']):
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                self.module.prepare(self.transport, self.config, self.plan)
        self.transport.run.assert_called_once()

    def test_missing_driver_fails_before_any_native_client_is_created(self):
        with patch.object(self.module, 'qualify_console'), \
                patch.object(self.module, 'shell', side_effect=[b'test\n', b'', RuntimeError('missing driver')]):
            with patch.object(self.module, 'NativeClient') as native:
                with self.assertRaisesRegex(RuntimeError, 'missing driver'):
                    self.module.verify_desktop('verify', self.config, self.plan, Mock(), self.transport,
                                               Path('output'), Path('state'), False)
        native.assert_not_called()

    def test_healthy_native_permissions_do_not_enter_repair(self):
        self.plan.checks = []
        self.plan.wda_service = 'com.example.wda'
        with patch.object(self.module, 'shell', return_value=b'test\n'), \
                patch.object(self.module, 'qualify_console'), \
                patch.object(self.module, 'signing_fingerprint', return_value='reviewed'), \
                patch.object(self.module, 'wait_wda'), patch.object(self.module, 'refresh_wda'), \
                patch.object(self.module, 'endpoint'), patch.object(self.module, 'NativeClient'), \
                patch.object(self.module, 'qualify', return_value={'input_readback': True}), \
                patch.object(self.module, 'PermissionRepair') as repair:
            result = self.module.verify_desktop('reconcile', self.config, self.plan, Mock(), self.transport,
                                                 Path('output'), Path('state'), False)
        repair.assert_not_called()
        self.assertTrue(result['native']['input_readback'])

    def test_locked_console_fails_before_native_session_creation(self):
        import plistlib
        value = {'IOConsoleLocked': True, 'IOConsoleUsers': [
            {'kCGSSessionOnConsoleKey': True, 'kCGSSessionUserNameKey': 'test',
             'CGSSessionScreenIsLocked': True}]}
        with patch.object(self.module, 'shell', return_value=plistlib.dumps(value)):
            with self.assertRaisesRegex(RuntimeError, 'locked'):
                self.module.require_unlocked_console(self.transport, 'test')

    def test_only_an_unlocked_matching_console_is_accepted(self):
        import plistlib
        value = {'IOConsoleLocked': False, 'IOConsoleUsers': [
            {'kCGSSessionOnConsoleKey': True, 'kCGSSessionUserNameKey': 'test',
             'CGSSessionScreenIsLocked': False}]}
        with patch.object(self.module, 'shell', return_value=plistlib.dumps(value)):
            self.module.require_unlocked_console(self.transport, 'test')
            with self.assertRaisesRegex(RuntimeError, 'ambiguous'):
                self.module.require_unlocked_console(self.transport, 'other')

    def test_verify_never_authenticates_a_locked_session(self):
        with patch.object(self.module, 'console_state', return_value=(True, {})), \
                patch.object(self.module, 'MacConsole') as console:
            with self.assertRaisesRegex(RuntimeError, 'locked'):
                self.module.qualify_console('verify', self.config, self.plan, Mock(), self.transport, Path('output'))
        console.assert_not_called()

    def test_reconcile_authenticates_once_then_requires_actual_unlock(self):
        session = {'CGSSessionScreenIsLocked': True, 'kCGSSessionSecureInputPID': 123,
                   'kCGSessionLongUserNameKey': 'Test'}
        config = {**self.config, 'qmp_port': 1234, 'macos': {'tesseract': 'tesseract'}}
        with patch.object(self.module, 'console_state', side_effect=[(True, session), (False, session)]), \
                patch.object(self.module, 'shell', return_value=b'/System/Library/CoreServices/loginwindow.app/Contents/MacOS/loginwindow'), \
                patch.object(self.module, 'MacConsole') as console:
            self.module.qualify_console('reconcile', config, self.plan, Mock(), self.transport, Path('output'))
        console.return_value.unlock.assert_called_once()
        self.assertEqual(console.return_value.unlock.call_args.args[:2], ('Test', 'synthetic-secret'))

    def test_unreviewed_secure_input_process_never_receives_a_credential(self):
        session = {'CGSSessionScreenIsLocked': True, 'kCGSSessionSecureInputPID': 123,
                   'kCGSessionLongUserNameKey': 'Test'}
        with patch.object(self.module, 'console_state', return_value=(True, session)), \
                patch.object(self.module, 'shell', return_value=b'/Applications/Other.app/Other'), \
                patch.object(self.module, 'MacConsole') as console:
            with self.assertRaisesRegex(RuntimeError, 'loginwindow'):
                self.module.qualify_console('reconcile', self.config, self.plan, Mock(), self.transport, Path('output'))
        console.assert_not_called()

    def test_authorization_identity_requires_a_reviewed_system_process_and_account(self):
        session = {'kCGSSessionSecureInputPID': 123}
        executables = (
            '/System/Applications/System Settings.app/Contents/MacOS/System Settings',
            '/System/Library/Frameworks/Security.framework/Versions/A/MachServices/'
            'SecurityAgent.bundle/Contents/MacOS/SecurityAgent',
        )
        for executable in executables:
            record = '501 timestamp ' + executable
            with self.subTest(executable=executable), \
                    patch.object(self.module, 'console_state', return_value=(False, session)), \
                    patch.object(self.module, 'shell', side_effect=[b'501', record.encode()]):
                self.assertEqual(self.module.authorization_identity(self.transport, 'test'), (123, record))
        for locked, record in ((True, '501 timestamp ' + executables[0]),
                               (False, '501 timestamp /Applications/Other.app/Other'),
                               (False, '502 timestamp ' + executables[0])):
            with self.subTest(locked=locked, record=record), \
                    patch.object(self.module, 'console_state', return_value=(locked, session)), \
                    patch.object(self.module, 'shell', side_effect=[b'501', record.encode()]):
                with self.assertRaises(RuntimeError):
                    self.module.authorization_identity(self.transport, 'test')

    def test_old_wda_listener_is_not_accepted_as_a_completed_restart(self):
        self.plan.wda_url = 'http://127.0.0.1:10100'
        with patch.object(self.module, 'wda_listener', side_effect=[100, 200]) as listener:
            with patch.object(self.module, 'shell', return_value=b'{"value":{"ready":true}}') as shell:
                with patch.object(self.module.time, 'sleep'):
                    self.module.wait_wda(self.transport, self.plan, Mock(), previous_pid=100)
        self.assertEqual(listener.call_count, 2)
        shell.assert_called_once()

    def test_cli_cancellation_uses_the_shared_owner_and_restores_signals(self):
        previous = signal.getsignal(signal.SIGINT)
        owners = []

        def operation(_action, _config, _plan, _repair, *, owner):
            owners.append(owner)
            self.assertIs(owner.cancellation, current_cancellation())
            with owner:
                owner.cancellation.request(signal.SIGINT)
                owner.checkpoint()

        with patch.object(sys, 'argv', ['macos-desktop.py', 'verify', 'guest.json', '--plan', 'plan.json']):
            with patch.object(self.module, 'guest_config'), patch.object(self.module, 'desktop_plan'):
                with patch.object(self.module, 'run', side_effect=operation):
                    with patch.object(self.module, 'report_cleanup'):
                        self.assertEqual(self.module.main(), 130)
        self.assertIs(owners[0].state, OwnerState.RELEASED)
        self.assertIs(signal.getsignal(signal.SIGINT), previous)


if __name__ == '__main__':
    unittest.main()
