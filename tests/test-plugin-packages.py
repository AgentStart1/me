#!/usr/bin/env python3
"""Independent distribution integrity, regeneration and output safety contracts."""
import importlib.util
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('validation', ROOT / 'scripts/validate-plugin-packages.py')
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)
build = validation.builder.build


class PackageTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def source_fixture(self):
        fixture = self.root / 'source'
        shutil.copytree(ROOT / 'plugins', fixture / 'plugins')
        shutil.copytree(ROOT / 'scripts/templates', fixture / 'scripts/templates')
        return fixture

    def test_distribution_integrity_and_runtime_resources(self):
        for client in ('claude', 'codex'):
            with self.subTest(client=client):
                output = self.root / ('me.' + client)
                build(client, output)
                validation.validate(client, output)
                for name in ('qemu-guests', 'android-emulator-profile', 'android-device-lock'):
                    plugin = output / 'plugins' / name
                    manifest = json.loads((plugin / f'.{client}-plugin/plugin.json').read_text())
                    self.assertEqual(manifest['mcpServers'], './.mcp.json')
                    for resource in ('.mcp.json', 'templates/status-panel.html', 'scripts/status-server.py'):
                        self.assertTrue((plugin / resource).is_file(), str(plugin / resource))
                self.assertTrue((output / 'plugins/qemu-guests/container/Dockerfile').is_file())
                self.assertTrue((output / 'plugins/qemu-guests/skills/qemu-guests/references/configuration-and-recovery.md').is_file())

    def test_regeneration_removes_stale_content_and_preserves_unrelated_files(self):
        for client in ('claude', 'codex'):
            with self.subTest(client=client):
                output = self.root / ('me.' + client)
                output.mkdir()
                (output / 'unrelated.txt').write_text('keep')
                build(client, output)
                before = {p.relative_to(output): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in output.rglob('*') if p.is_file()}
                marketplace = output / ('.agents/plugins' if client == 'codex' else '.claude-plugin')
                (marketplace / 'stale.txt').write_text('stale')
                stale = output / 'plugins/stale'
                stale.mkdir()
                (stale / 'stale.txt').write_text('stale')
                build(client, output)
                after = {p.relative_to(output): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in output.rglob('*') if p.is_file()}
                self.assertEqual(before, after)
                self.assertEqual((output / 'unrelated.txt').read_text(), 'keep')

    def test_unsafe_output_paths_are_rejected(self):
        for client in ('codex', 'claude'):
            for unsafe in (ROOT, ROOT.parent, ROOT / ('me.' + client)):
                with self.subTest(client=client, path=str(unsafe)):
                    with self.assertRaises(ValueError):
                        build(client, unsafe)

    def test_invalid_agent_route_preserves_existing_output(self):
        fixture = self.source_fixture()
        output = self.root / 'me.claude'
        output.mkdir()
        (output / 'README.md').write_text('preserve before validation')
        manifest_path = fixture / 'plugins/android-device-lock/plugin.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['extensions']['com.anthropic.claude']['skillFrontmatter']['android-device-lock']['agent'] = 'missing-agent'
        manifest_path.write_text(json.dumps(manifest))
        with patch.object(validation.builder, 'ROOT', fixture):
            with self.assertRaisesRegex(ValueError, 'missing Claude agent'):
                build('claude', output)
        self.assertEqual((output / 'README.md').read_text(), 'preserve before validation')

    def test_development_artifacts_are_excluded_from_bundled_resources(self):
        fixture = self.source_fixture()
        for relative in ('ui/node_modules/dependency/index.js', 'scripts/__pycache__/status.pyc',
                         'skills/qemu-guests/node_modules/dependency/index.js'):
            artifact = fixture / 'plugins/qemu-guests' / relative
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text('development artifact')
        with patch.object(validation.builder, 'ROOT', fixture):
            for client in ('codex', 'claude'):
                with self.subTest(client=client):
                    output = self.root / ('me.' + client)
                    build(client, output)
                    self.assertEqual(list(output.rglob('node_modules')), [])
                    self.assertEqual(list(output.rglob('__pycache__')), [])
                    self.assertTrue((output / 'plugins/qemu-guests/templates/status-panel.html').is_file())


if __name__ == '__main__':
    unittest.main()
