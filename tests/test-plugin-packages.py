#!/usr/bin/env python3
"""Check distribution integrity, regeneration, and destructive-path guards."""
import importlib.util
from pathlib import Path
import tempfile

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
print('Distribution integrity, determinism, and path guards passed.')
