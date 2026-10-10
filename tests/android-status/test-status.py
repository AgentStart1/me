# /// script
# requires-python = ">=3.10"
# dependencies = ["openai-mcp-extensions==0.1.0", "mcp==2.2.0"]
# ///
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
EMULATOR = ROOT / 'plugins/android-emulator-profile'
LOCKS = ROOT / 'plugins/android-device-lock'
sys.path[:0] = [str(EMULATOR / 'scripts'),str(LOCKS / 'scripts')]
import android_probe
import emulator_status
import lock_status
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg=='
DEVICE = {'serial':'emulator-5554','avd':'test-avd','png':PNG}


class Fixture:
    def __init__(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.config = self.root / 'devices.json'
        self.log = self.root / 'commands.jsonl'
        self.avds = self.root / 'avd'
        self.avds.mkdir()
        self.adb = self.root / 'adb'
        source = (ROOT / 'tests/android-status/fake-adb.py').read_text()
        self.adb.write_text('#!' + sys.executable + '\n' + source.split('\n',1)[1])
        self.adb.chmod(0o755)
        if os.name == 'nt':
            script = self.adb
            self.adb = self.root / 'adb.cmd'
            self.adb.write_text(f'@"{sys.executable}" "{script}" %*\n')
        self.env = {'ANDROID_ADB_COMMAND':str(self.adb), 'ANDROID_AVD_HOME':str(self.avds),
                    'FAKE_ADB_CONFIG':str(self.config), 'FAKE_ADB_LOG':str(self.log),
                    'PYTHONDONTWRITEBYTECODE':'1', 'ANDROID_DEVICE_LOCK_PATH':lock_status.DEFAULT_LOCK_PATH}
        self.write([DEVICE])
    def write(self, devices, **kwargs): self.config.write_text(json.dumps({'devices':devices,**kwargs}))
    def inventory(self):
        directory = self.avds / 'test-avd.avd'; directory.mkdir()
        (self.avds / 'test-avd.ini').write_text(f'path={directory}\ntarget=android-35\n')
        (directory / 'config.ini').write_text('abi.type=x86_64\nhw.ramSize=2048\nhw.lcd.width=1080\nhw.lcd.height=2400\n')
    def commands(self): return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
    def close(self): self.directory.cleanup()


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.fixture=Fixture();self.environment=patch.dict(os.environ,self.fixture.env);self.environment.start()
    def tearDown(self): self.environment.stop();self.fixture.close()
    def test_configured_online_emulator_and_physical_device_filtering(self):
        self.fixture.inventory()
        self.fixture.write([DEVICE,{'serial':'phone','qemu':'0'}])
        status=emulator_status.collect_status()
        self.assertEqual(len(status['emulators']),1)
        self.assertEqual(status['emulators'][0]['state'],'online')
        self.assertEqual(status['emulators'][0]['abi'],'x86_64')
        self.assertFalse(any('exec-out' in command for command in self.fixture.commands()))
    def test_booting_offline_and_unavailable_adb_are_not_stopped(self):
        self.fixture.inventory()
        self.fixture.write([{**DEVICE,'boot':'0'}])
        self.assertEqual(emulator_status.collect_status()['emulators'][0]['state'],'booting')
        self.fixture.write([{**DEVICE,'connection':'offline'}])
        status=emulator_status.collect_status()
        self.assertEqual(status['emulators'][0]['state'],'unknown')
        self.assertEqual(status['emulators'][1]['state'],'offline')
        self.fixture.write([],fail=True)
        status=emulator_status.collect_status()
        self.assertEqual(status['adb']['state'],'unavailable')
        self.assertEqual(status['emulators'][0]['state'],'unknown')
    def test_successfully_observed_absent_emulator_is_disconnected(self):
        self.fixture.inventory();self.fixture.write([])
        self.assertEqual(emulator_status.collect_status()['emulators'][0]['state'],'disconnected')
    def test_screenshot_is_serial_scoped_and_rejects_physical_offline_and_injection(self):
        self.assertEqual(emulator_status.screenshot(DEVICE['serial']),PNG)
        self.assertIn(['-s','emulator-5554','exec-out','screencap','-p'],self.fixture.commands())
        self.fixture.write([{'serial':'phone','qemu':'0','png':PNG},{**DEVICE,'connection':'unauthorized'}])
        for serial in ['phone','emulator-5554','-s attacker','serial;touch /tmp/marker']:
            with self.assertRaises(android_probe.ProbeError): emulator_status.screenshot(serial)
    def test_timeout_does_not_expose_subprocess_output(self):
        with patch.object(android_probe.subprocess,'run',side_effect=subprocess.TimeoutExpired(['adb'],5)):
            with self.assertRaisesRegex(android_probe.ProbeError,'timed out'): android_probe.adb(['devices','-l'])
    def test_lock_states_redaction_and_offline_probe(self):
        metadata={'expires_at_epoch':4102444800,'owner_token':'do-not-expose','test_name':'login','host':'runner','pid':7,'project_dir':'C:\\private\\project','acquired_at_utc':'2026-10-01T00:00:00Z'}
        self.fixture.write([{**DEVICE,'lock':'present\n'+json.dumps(metadata)}, {'serial':'phone','connection':'offline'}])
        snapshot=lock_status.collect_status();lease=snapshot['devices'][0]['lock']
        self.assertEqual(lease['state'],'held');self.assertEqual(lease['project'],'project')
        self.assertNotIn('do-not-expose',json.dumps(snapshot));self.assertNotIn('private',json.dumps(snapshot))
        self.assertEqual(snapshot['devices'][1]['lock']['state'],'unavailable')
        self.assertFalse(any(command[:2]==['-s','phone'] for command in self.fixture.commands()))
    def test_missing_expired_corrupt_and_inaccessible_locks_are_distinct(self):
        self.assertEqual(lock_status.parse_lock('absent\n',100)['state'],'free')
        self.assertEqual(lock_status.parse_lock('present\n{"expires_at_epoch":99}',100)['state'],'expired')
        for raw in ['present\n','present\n{}','present\nnot-json','present\n[]','unknown\n','invalid\n','present\n{"expires_at_epoch":true}']:
            self.assertEqual(lock_status.parse_lock(raw,100)['state'],'unknown',raw)
    def test_remote_read_quotes_paths_and_never_changes_lease(self):
        directory=self.fixture.root / "space '; printf injected; '"
        directory.mkdir();metadata=directory/'lock.json';metadata.write_text('{"expires_at_epoch":200}')
        before=metadata.read_bytes()
        result=subprocess.run(['sh','-c',lock_status.read_command(str(directory))],capture_output=True,text=True,check=True)
        self.assertEqual(lock_status.parse_lock(result.stdout,100)['state'],'held')
        self.assertEqual(metadata.read_bytes(),before)
        self.assertNotIn('injected',result.stdout)
    def test_adb_permission_failure_keeps_ownership_unavailable(self):
        self.fixture.write([{'serial':'phone','connection':'no permissions'}])
        snapshot=lock_status.collect_status()
        self.assertEqual(snapshot['devices'][0]['connection'],'no permissions')
        self.assertEqual(snapshot['devices'][0]['lock']['state'],'unavailable')

    def test_ipv6_serials_remain_available_alongside_other_devices(self):
        serials = ['emulator-5554', '[::1]:5555', '[fe80::1%eth0]:5555']
        self.fixture.write([{**DEVICE, 'serial': serial} for serial in serials])
        snapshot = lock_status.collect_status()
        self.assertEqual(snapshot['adb']['state'], 'available')
        self.assertEqual([item['serial'] for item in snapshot['devices']], serials)
        self.assertEqual(snapshot['warnings'], [])
        for serial in serials:
            self.assertTrue(any(command[:2] == ['-s', serial] for command in self.fixture.commands()))

    def test_bad_device_records_do_not_hide_valid_devices(self):
        output = 'List of devices attached\ninvalid-row\n???????????? no permissions\nemulator-5554 device model:Pixel\n'
        with patch.object(android_probe, 'adb', return_value=output):
            status, items, warnings = android_probe.collect_devices(lambda device: device)
        self.assertEqual(status['state'], 'available')
        self.assertEqual([item['serial'] for item in items], ['emulator-5554'])
        self.assertEqual(len(warnings), 2)
        self.assertNotIn('????????????', json.dumps(warnings))

    def test_lease_timing_uses_end_of_batch_for_all_devices(self):
        current = [100]
        leases = {'first': 105, 'second': 130}
        def probe(args, serial):
            return 'present\n' + json.dumps({'expires_at_epoch': leases[serial]})
        def collect(inspect):
            first = inspect({'serial': 'first', 'connection': 'device'})
            current[0] = 110  # Another device delays the completed snapshot.
            second = inspect({'serial': 'second', 'connection': 'device'})
            current[0] = 120
            return {'state': 'available'}, [first, second], []
        with patch.object(lock_status, 'collect_devices', side_effect=collect), \
             patch.object(lock_status, 'adb', side_effect=probe), \
             patch.object(lock_status.time, 'time', side_effect=lambda: current[0]):
            snapshot = lock_status.collect_status()
        expired, held = [item['lock'] for item in snapshot['devices']]
        self.assertEqual((expired['state'], expired['remainingSeconds']), ('expired', 0))
        self.assertEqual((held['state'], held['remainingSeconds']), ('held', 10))

    def test_unavailable_adb_does_not_claim_no_devices(self):
        self.fixture.write([],fail=True)
        self.assertEqual(lock_status.collect_status()['adb']['state'],'unavailable')


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_global_and_thread_entrypoints_and_app_only_screenshot(self):
        fixture=Fixture()
        try:
            for plugin,name,title in [(EMULATOR,'android_emulator_status','Android Emulators'),(LOCKS,'android_device_lock_status','Device Leases')]:
                parameters=StdioServerParameters(command=sys.executable,args=[str(plugin/'scripts/status-server.py')],env={**os.environ,**fixture.env})
                async with stdio_client(parameters) as (read,write):
                    async with ClientSession(read,write) as client:
                        await client.initialize()
                        tools={tool.name:tool for tool in (await client.list_tools()).tools}
                        tool=tools[name]
                        self.assertTrue(tool.annotations.read_only_hint)
                        self.assertEqual(tool.meta['openai/ui']['entrypoints'],[{'type':'global'},{'type':'thread'}])
                        resource=await client.read_resource(tool.meta['ui']['resourceUri'])
                        self.assertIn(title,resource.contents[0].text)
                        self.assertNotIn('/* PANEL_SCRIPT */',resource.contents[0].text)
                        result=await client.call_tool(name,{})
                        self.assertFalse(result.is_error)
                        self.assertEqual(result.structured_content['adb']['state'],'available')
                        self.assertNotIn('owner_token',json.dumps(result.structured_content))
                        if plugin==EMULATOR:
                            self.assertEqual(tools['android_emulator_screenshot'].meta['ui']['visibility'],['app'])
                            result=await client.call_tool('android_emulator_screenshot',{'serial':'emulator-5554'})
                            self.assertFalse(result.is_error)
                            self.assertEqual(result.content[0].data,PNG)
        finally: fixture.close()


if __name__=='__main__': unittest.main()
