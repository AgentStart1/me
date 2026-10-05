#!/usr/bin/env python3
"""Check distribution integrity, regeneration, and destructive-path guards."""
import importlib.util
from pathlib import Path
import tempfile
import json
import shutil

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('validation', ROOT / 'scripts/validate-plugin-packages.py')
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)
build = validation.builder.build
with tempfile.TemporaryDirectory() as temporary:
    for client in ['claude', 'codex']:
        output = Path(temporary) / f'me.{client}'
        output.mkdir()
        (output / 'unrelated.txt').write_text('keep')
        build(client, output)
        validation.validate(client, output)
        for name in ['qemu-alpine-docker', 'android-emulator-profile', 'android-appium-device-lock']:
            plugin = output / 'plugins' / name
            manifest = json.loads((plugin / f'.{client}-plugin/plugin.json').read_text())
            assert manifest['mcpServers'] == './.mcp.json'
            for resource in ['.mcp.json', 'templates/status-panel.html', 'scripts/status-server.py']:
                assert (plugin / resource).is_file(), f'missing status runtime: {plugin / resource}'
        assert (output / 'plugins/qemu-alpine-docker/container/Dockerfile').is_file()
        assert (output / 'plugins/qemu-alpine-docker/skills/qemu-alpine-docker/references/configuration-and-recovery.md').is_file()
        before = {p.relative_to(output): p.read_bytes() for p in output.rglob('*') if p.is_file()}
        marketplace_dir = output / ('.agents/plugins' if client == 'codex' else '.claude-plugin')
        (marketplace_dir / 'stale.txt').write_text('stale')
        stale = output / 'plugins/stale'
        stale.mkdir()
        (stale / 'stale.txt').write_text('stale')
        build(client, output)
        after = {p.relative_to(output): p.read_bytes() for p in output.rglob('*') if p.is_file()}
        assert before == after, 'regeneration is not deterministic'
        assert (output / 'unrelated.txt').read_text() == 'keep'
    for unsafe in [ROOT, ROOT.parent, ROOT / 'me.codex']:
        try:
            build('codex', unsafe)
        except ValueError:
            pass
        else:
            raise AssertionError(f'accepted unsafe output: {unsafe}')
# Invalid extension routes must fail before replacing existing output.
with tempfile.TemporaryDirectory() as temporary:
    fixture = Path(temporary) / 'source'
    fixture.mkdir()
    shutil.copytree(ROOT / 'plugins', fixture / 'plugins')
    output = Path(temporary) / 'me.claude'
    output.mkdir()
    (output / 'README.md').write_text('preserve before validation')
    original_root = validation.builder.ROOT
    validation.builder.ROOT = fixture
    manifest_path = fixture / 'plugins/android-appium-device-lock/plugin.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['extensions']['com.anthropic.claude']['skillFrontmatter']['android-appium-device-lock']['agent'] = 'missing-agent'
    manifest_path.write_text(json.dumps(manifest))
    try:
        try:
            build('claude', output)
        except ValueError as error:
            assert 'missing Claude agent' in str(error)
        else:
            raise AssertionError('accepted missing agent route')
        assert (output / 'README.md').read_text() == 'preserve before validation'
    finally:
        validation.builder.ROOT = original_root
print('Distribution integrity, routing, determinism, and path guards passed.')

# Development artifacts must be excluded even inside bundled skill resources.
with tempfile.TemporaryDirectory() as temporary:
    fixture = Path(temporary) / 'source'
    shutil.copytree(ROOT / 'plugins', fixture / 'plugins')
    shutil.copytree(ROOT / 'scripts/templates', fixture / 'scripts/templates')
    plugin = fixture / 'plugins/qemu-alpine-docker'
    for relative in ['ui/node_modules/dependency/index.js', 'scripts/__pycache__/status.pyc',
                     'skills/qemu-alpine-docker/node_modules/dependency/index.js']:
        artifact = plugin / relative
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text('development artifact')
    original_root = validation.builder.ROOT
    validation.builder.ROOT = fixture
    try:
        for client in ['codex', 'claude']:
            output = Path(temporary) / f'me.{client}'
            build(client, output)
            assert not list(output.rglob('node_modules'))
            assert not list(output.rglob('__pycache__'))
            assert (output / 'plugins/qemu-alpine-docker/templates/status-panel.html').is_file()
    finally:
        validation.builder.ROOT = original_root
print('Status runtime registration and development artifact exclusion passed.')
