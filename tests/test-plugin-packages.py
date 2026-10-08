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
