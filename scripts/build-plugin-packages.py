#!/usr/bin/env python3
"""Generate client distributions from portable plugin manifests."""
import argparse
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = {'name', 'version', 'description', 'author', 'homepage', 'repository', 'license', 'keywords'}
NAMESPACES = {'codex': 'com.openai.codex', 'claude': 'com.anthropic.claude'}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def build(client, output):
    output = output.resolve()
    # Never delete source, its ancestors, or nested source content.
    if output == ROOT or output in ROOT.parents or ROOT in output.parents:
        raise ValueError('output must be outside the source repository')
    if output.name != f'me.{client}':
        raise ValueError(f'output directory must be named me.{client}')
    manifests = [(p.parent, json.loads(p.read_text())) for p in sorted((ROOT / 'plugins').glob('*/plugin.json'))]
    if not manifests:
        raise ValueError('no portable plugins found')
    for source, manifest in manifests:
        if manifest['name'] != source.name:
            raise ValueError(f'plugin name does not match directory: {source}')
    marketplace_dir = output / ('.agents/plugins' if client == 'codex' else '.claude-plugin')
    for owned in [output / 'plugins', marketplace_dir]:
        if owned.is_symlink():
            raise ValueError(f'refusing symlink output: {owned}')
    for owned in [output / 'plugins', marketplace_dir]:
        if owned.exists():
            shutil.rmtree(owned)
    entries = []
    for source, portable in manifests:
        destination = output / 'plugins' / source.name
        shutil.copytree(source, destination, ignore=shutil.ignore_patterns('.git', '.codex-plugin', '.claude-plugin', 'build'))
        (destination / 'plugin.json').unlink()
        if client == 'codex':
            shutil.rmtree(destination / 'agents', ignore_errors=True)
            for skill in (destination / 'skills').glob('*/SKILL.md'):
                content = skill.read_text()
                match = re.match(r'^---\n(.*?)\n---', content, re.S)
                if not match:
                    raise ValueError(f'missing frontmatter: {skill}')
                frontmatter = re.sub(r'^(context|agent):[^\n]*\n?', '', match[1], flags=re.M)
                skill.write_text('---\n' + frontmatter.rstrip() + '\n---' + content[match.end():])
        manifest = {k: v for k, v in portable.items() if k in CORE}
        extra = portable.get('extensions', {}).get(NAMESPACES[client], {})
        if set(extra) & CORE:
            raise ValueError('client extensions cannot override portable identity')
        manifest.update(extra)
        write_json(destination / f'.{client}-plugin/plugin.json', manifest)
        if client == 'codex':
            entries.append({'name': source.name, 'source': {'source': 'local', 'path': f'./plugins/{source.name}'}, 'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_INSTALL'}, 'category': extra.get('interface', {}).get('category', 'Developer Tools')})
        else:
            entries.append({'name': source.name, 'source': f'./plugins/{source.name}'})
    marketplace = {'name': 'me', 'plugins': entries}
    if client == 'codex':
        marketplace['interface'] = {'displayName': 'Me'}
    else:
        marketplace['owner'] = {'name': 'storytellerF'}
        marketplace['description'] = 'Portable Android tooling, coding guidance, and report sharing plugins.'
    write_json(marketplace_dir / 'marketplace.json', marketplace)
    template = ROOT / 'scripts/templates' / f'{client}-readme.md.template'
    (output / 'README.md').write_text(template.read_text())
    print(f'Generated {len(entries)} {client} plugins in {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', required=True, choices=NAMESPACES)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    build(args.client, args.output_dir or ROOT.parent / f'me.{args.client}')
