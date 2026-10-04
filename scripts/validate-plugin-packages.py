#!/usr/bin/env python3
"""Validate portable identities, client manifests, resources, and Claude routing."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import yaml
import jsonschema

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('builder', ROOT / 'scripts/build-plugin-packages.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
spec = importlib.util.spec_from_file_location('skills', ROOT / 'scripts/validate-generated-codex-skills.py')
skills = importlib.util.module_from_spec(spec)
spec.loader.exec_module(skills)


def frontmatter(path):
    content = path.read_text()
    match = re.match(r'^---\n(.*?)\n---', content, re.S)
    assert match, f'missing frontmatter: {path}'
    return yaml.safe_load(match[1])


def validate(client, output):
    schema = json.loads((ROOT / 'scripts/schemas/plugin.schema.json').read_text())
    sources = sorted((ROOT / 'plugins').glob('*/plugin.json'))
    marketplace_path = output / ('.agents/plugins' if client == 'codex' else '.claude-plugin') / 'marketplace.json'
    marketplace = json.loads(marketplace_path.read_text())
    assert marketplace['name'] == 'me'
    names = [p.parent.name for p in sources]
    assert sorted(p['name'] for p in marketplace['plugins']) == names
    assert sorted(p.name for p in (output / 'plugins').iterdir()) == names
    for entry in marketplace['plugins']:
        expected = './plugins/' + entry['name']
        assert (entry['source']['path'] if client == 'codex' else entry['source']) == expected
    for path in sources:
        portable = json.loads(path.read_text())
        jsonschema.Draft202012Validator(schema).validate(portable)
        assert re.fullmatch(r'\d+\.\d+\.\d+-\d{14}', portable['version'])
        for namespace in portable.get('extensions', {}):
            assert re.fullmatch(r'[a-z][a-z0-9]*(?:\.[a-z][a-z0-9-]*)+', namespace)
        source = path.parent
        generated = output / 'plugins' / source.name
        manifest = json.loads((generated / f'.{client}-plugin/plugin.json').read_text())
        expected = {k: v for k, v in portable.items() if k in builder.CORE}
        expected.update(portable['extensions'][builder.NAMESPACES[client]])
        assert manifest == expected, f'manifest mismatch: {source.name}'
        assert not (generated / 'plugin.json').exists()
        assert not (generated / f'.{"claude" if client == "codex" else "codex"}-plugin').exists()
        for file in source.rglob('*'):
            if not file.is_file() or file == path or 'build' in file.relative_to(source).parts:
                continue
            relative = file.relative_to(source)
            if client == 'codex' and relative.parts[0] == 'agents':
                assert not (generated / relative).exists()
                continue
            copy = generated / relative
            assert copy.is_file(), f'missing resource: {copy}'
            if client == 'codex' and file.name == 'SKILL.md':
                assert not skills.validate_skill(copy.parent), f'invalid skill: {copy}'
                assert frontmatter(copy) == {k: v for k, v in frontmatter(file).items() if k not in {'context', 'agent'}}
                source_body = re.split(r'^---$', file.read_text(), maxsplit=2, flags=re.M)[2]
                copied_body = re.split(r'^---$', copy.read_text(), maxsplit=2, flags=re.M)[2]
                assert copied_body == source_body, f'changed instructions: {copy}'
            else:
                assert copy.read_bytes() == file.read_bytes(), f'changed resource: {copy}'
        for skill in (source / 'skills').glob('*/SKILL.md'):
            metadata = frontmatter(skill)
            assert metadata['name'] == skill.parent.name
            if metadata.get('agent'):
                assert metadata.get('context') == 'fork'
                assert (source / 'agents' / (metadata['agent'] + '.md')).is_file()
        for agent in (source / 'agents').glob('*.md'):
            assert set(frontmatter(agent)) <= {'name', 'description', 'model', 'effort'}
    print(f'Validated portable sources and {len(sources)} generated {client} plugins.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', required=True, choices=builder.NAMESPACES)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    validate(args.client, args.output)
