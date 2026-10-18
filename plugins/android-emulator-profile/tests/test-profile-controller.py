"""Native fake-emulator lifecycle and literal profile contracts."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import profile_controller as profiles


class ProfileTests(unittest.TestCase):
    def test_literal_profiles_and_crlf(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quoted.profile"
            path.write_bytes(b"# comment\r\nAVD_NAME='with spaces'\r\nTEST=value; touch ignored\r\n")
            self.assertEqual(profiles.load_profile(path), {'AVD_NAME': 'with spaces', 'TEST': 'value; touch ignored'})
            for value in ('$(touch ignored)', '${HOME}', '`touch ignored`', '"unmatched'):
                path.write_text('KEY=' + value)
                with self.assertRaises(ValueError):
                    profiles.load_profile(path)

    def test_arguments_and_duplicate_ini(self):
        values = {'EMULATOR_FLAG_Mixed_Case': 'true', 'EMULATOR_VALUE_Custom_Value': 'space 名称',
                  'EMULATOR_FLAG_verbose': 'false'}
        self.assertEqual(profiles.arguments(values, 'EMULATOR', '-'), ['-Mixed-Case', '-Custom-Value', 'space 名称'])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.ini'
            path.write_text('duplicate.key=old\nduplicate.key=second\nkeep=yes\n')
            profiles.apply_config(path, {'EMULATOR_CONFIG_duplicate__key': 'new'})
            self.assertEqual(path.read_text(), 'duplicate.key=new\nkeep=yes\n')

    def test_native_lifecycle(self):
        with tempfile.TemporaryDirectory(prefix='avd fixture ') as directory:
            root = Path(directory)
            avd = root / '名称.avd'
            avd.mkdir()
            config = avd / 'config.ini'
            config.write_text('disk.dataPartition.size=2G\n')
            script = root / 'fixture.py'
            script.write_text('import json,os,sys,time\nfrom pathlib import Path\n'
                              'Path(os.environ["FIXTURE_LOG"]).write_text(json.dumps(sys.argv[1:]))\n'
                              'time.sleep(60) if os.environ.get("FIXTURE_HOLD") else None\n'
                              'sys.exit(int(os.environ.get("FIXTURE_STATUS", "0")))\n')
            executable = root / ('emulator.cmd' if os.name == 'nt' else 'emulator')
            if os.name == 'nt':
                executable.write_text(f'@echo off\n"{sys.executable}" "{script}" %*\n')
            else:
                executable.write_text(f'#!{sys.executable}\nexec(compile(open({str(script)!r}).read(), {str(script)!r}, "exec"))\n')
                executable.chmod(0o755)
            profile = root / 'test.profile'
            profile.write_text(f'AVD_NAME=名称\nAVDMANAGER_VALUE_path="{avd}"\nEMULATOR_VALUE_Custom_Value="space value"\n', encoding='utf-8')
            log = root / 'args.json'
            env = {**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH'], 'FIXTURE_LOG': str(log)}
            command = [sys.executable, str(SCRIPTS / 'start-avd.py'), str(profile)]
            result = subprocess.run(command, env={**env, 'FIXTURE_STATUS': '23'}, capture_output=True)
            self.assertEqual(result.returncode, 23, result.stderr)
            self.assertEqual(json.loads(log.read_text()), ['-avd', '名称', '-Custom-Value', 'space value'])
            guard = avd / 'config.ini.profile-start.guard'
            self.assertFalse(guard.exists())
            native_lock = avd / 'hardware-qemu.ini.lock'
            native_lock.mkdir()
            self.assertEqual(subprocess.run(command, env=env, capture_output=True).returncode, 1)
            self.assertTrue(native_lock.exists())
            native_lock.rmdir()
            log.unlink()
            process = subprocess.Popen(command, env={**env, 'FIXTURE_HOLD': '1'}, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
            try:
                deadline = time.monotonic() + 10
                while not log.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(.05)
                self.assertTrue(log.exists())
                contender = subprocess.run(command, env=env, capture_output=True)
                self.assertEqual(contender.returncode, 1)
                self.assertIn(b'guard is busy', contender.stderr)
                process.send_signal(signal.CTRL_BREAK_EVENT if os.name == 'nt' else signal.SIGTERM)
                self.assertEqual(process.wait(timeout=10), 128 + (signal.SIGBREAK if os.name == 'nt' else signal.SIGTERM))
                self.assertFalse(guard.exists())
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                process.stderr.close()


if __name__ == '__main__':
    unittest.main()
