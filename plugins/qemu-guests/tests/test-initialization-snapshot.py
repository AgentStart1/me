"""Fingerprint, seed payload and persisted metadata share one immutable input."""
from dataclasses import FrozenInstanceError
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from guest_seed import payload, prepare_seed
from test_requirements import apply, load


class InitializationSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.script = self.root / 'setup.sh'; self.script.write_bytes(b'echo original\n')
        self.requirements = self.root / 'requirements.json'
        self.requirements.write_text(json.dumps({'version': 1, 'desktop': {'width': 1920, 'height': 1080},
            'platforms': {name: {'java': 21, 'packages': ['openjdk-21-jre'] if name == 'Linux' else [],
                'appium': {'version': '3.2.2', 'drivers': {}, 'plugins': {}},
                'hooks': {'guest_setup': [{'script': 'setup.sh', 'interpreter': 'bash',
                    'arguments': ['original'], 'timeout_seconds': 30}]}}
                for name in ['Linux', 'Windows']}}))
        self.key = self.root / 'access'; Path(str(self.key) + '.pub').write_text('ssh-ed25519 AAAA fixture')
        self.runtime = self.root / 'runtime.zip'; self.runtime.write_bytes(b'runtime fixture')

    def config(self, system='ubuntu'):
        return apply({'os': system, 'name': 'fixture', 'graphical': True, 'ssh_user': 'tester',
                      'access_key': str(self.key), 'appium': {'runtime_archive': str(self.runtime)}}, self.requirements)

    def test_seed_uses_captured_script_after_source_changes_on_either_platform(self):
        for system in ['ubuntu', 'windows']:
            with self.subTest(system=system):
                self.script.write_bytes(b'echo original\n'); config = self.config(system)
                fingerprint = config['runtime_requirements']['sha256']
                self.script.write_bytes(b'echo replacement\n')
                files = payload(config)
                self.assertEqual(files['project-setup-0.sh'], b'echo original\n')
                self.assertEqual(config['initialization_snapshot'].record()['sha256'], fingerprint)
                self.assertNotEqual(load(self.requirements, system)['sha256'], fingerprint)

    def test_seed_does_not_need_original_script_or_requirements_after_capture(self):
        config = self.config(); self.script.unlink(); self.requirements.unlink()
        self.assertEqual(payload(config)['project-setup-0.sh'], b'echo original\n')

    def test_requirements_and_selected_script_are_read_once(self):
        reads = {self.requirements: 0, self.script: 0}; original = Path.read_bytes
        def read(path):
            if path in reads:
                reads[path] += 1
                self.assertEqual(reads[path], 1, 'Mutable initialization input was read twice')
            return original(path)
        with patch.object(Path, 'read_bytes', read):
            config = self.config(); payload(config)
        self.assertEqual(list(reads.values()), [1, 1])

    def test_snapshot_is_immutable_and_detached_views_cannot_change_seed(self):
        config = self.config(); snapshot = config['initialization_snapshot']
        with self.assertRaises(FrozenInstanceError): snapshot.guest_files = ()
        view = snapshot.record(); view['runtime']['java'] = 99
        config['runtime_requirements']['runtime']['java'] = 98
        config['desktop']['width'] = 800
        files = payload(config)
        self.assertEqual(json.loads(files['runtime-requirements.json'])['java'], 21)
        self.assertEqual(json.loads(files['desktop.json'])['width'], 1920)
        self.assertEqual(json.loads(files['setup-hooks.json'])[0]['arguments'], ['original'])

    def test_configuration_changes_after_capture_do_not_change_payload_or_fingerprint(self):
        config = self.config(); before = config['initialization_snapshot'].record()
        data = json.loads(self.requirements.read_text()); data['desktop']['width'] = 1000
        data['platforms']['Linux']['hooks']['guest_setup'][0]['arguments'] = ['replacement']
        self.requirements.write_text(json.dumps(data))
        files = payload(config)
        self.assertEqual(json.loads(files['desktop.json'])['width'], 1920)
        self.assertEqual(json.loads(files['setup-hooks.json'])[0]['arguments'], ['original'])
        self.assertEqual(config['initialization_snapshot'].record(), before)
        self.assertNotEqual(load(self.requirements, 'ubuntu')['sha256'], before['sha256'])

    def test_cloud_init_packages_come_from_snapshot_not_mutable_views(self):
        config = self.config(); config['desktop']['packages'] = ['replacement-package']
        config['runtime_requirements']['desktop']['packages'] = ['another-package']
        prepare_seed(config, self.root / 'seed')
        cloud = json.loads((self.root / 'seed/user-data').read_text().split('\n', 1)[1])
        self.assertIn('openjdk-21-jre', cloud['packages'])
        self.assertNotIn('replacement-package', cloud['packages'])
        self.assertNotIn('another-package', cloud['packages'])

    def test_install_records_same_snapshot_as_actual_seed_bytes(self):
        spec = importlib.util.spec_from_file_location('snapshot_guest_vm', SCRIPTS / 'guest-vm.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        config = {**self.config(), 'base_image': 'fixture.qcow2', 'disk_size': '24G', 'media_sha256': 'fixture'}
        expected = config['initialization_snapshot'].record()
        self.script.write_bytes(b'echo replacement\n')
        config['runtime_requirements']['sha256'] = 'mutable-view-corruption'
        state = self.root / 'state'; state.mkdir()
        with patch.object(module, 'verify_inputs'), patch.object(module.subprocess, 'run'):
            module.initialize(config, state)
        record = json.loads((state / 'runtime-requirements.json').read_text())
        self.assertEqual(record, expected)
        with zipfile.ZipFile(state / 'seed/payload.zip') as archive:
            self.assertEqual(archive.read('project-setup-0.sh'), b'echo original\n')

    def test_hook_record_without_content_snapshot_cannot_reread_project_paths(self):
        config = self.config(); del config['initialization_snapshot']
        with self.assertRaisesRegex(ValueError, 'snapshot'): payload(config)

    def test_no_hook_fingerprint_remains_raw_requirements_digest(self):
        data = json.loads(self.requirements.read_text()); del data['platforms']['Linux']['hooks']
        self.requirements.write_text(json.dumps(data))
        self.assertEqual(self.config()['runtime_requirements']['sha256'],
                         hashlib.sha256(self.requirements.read_bytes()).hexdigest())


if __name__ == '__main__': unittest.main()
