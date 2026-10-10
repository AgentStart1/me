"""Ensure every plugin runtime suite remains connected to plugin test CI."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
workflow = ROOT / '.github/workflows/test-plugins.yml'
config = yaml.safe_load(workflow.read_text())
jobs = config['jobs']
package_config = yaml.safe_load((workflow.parent / 'validate-client-packages.yml').read_text())
assert config['name'] == 'Test plugins'
assert package_config['name'] == 'Validate client packages'
assert config['concurrency']['group'] != package_config['concurrency']['group']
assert 'packages' not in jobs
package_runs = '\n'.join(step.get('run', '') for job in package_config['jobs'].values()
                         for step in job['steps'])
for client in ['codex', 'claude']:
    assert f'build-{client}-plugin-package.sh' in package_runs
    assert f'validate-plugin-packages.py --client {client}' in package_runs
assert 'validate-generated-codex-skills.py' in package_runs
assert not (workflow.parent / 'validate-plugins.yml').exists()
assert jobs['sharing']['strategy']['fail-fast'] is False
sharing = jobs['sharing']['strategy']['matrix']['plugin']
runs = '\n'.join(step.get('run', '') for job in jobs.values() for step in job['steps'])
for plugin in sharing:
    assert list((ROOT / 'plugins' / plugin / 'tests').glob('test-*.sh'))
    runs += '\n' + '\n'.join(str(p.relative_to(ROOT)).replace('\\', '/') for p in
                              (ROOT / 'plugins' / plugin / 'tests').glob('test-*.sh'))
for directory in [*ROOT.glob('plugins/*/tests'), ROOT / 'tests/android-status']:
    for test in directory.glob('test-*'):
        if test.suffix in {'.sh', '.py'}:
            assert test.relative_to(ROOT).as_posix() in runs, f'CI does not run {test}'
for package in [ROOT / 'scripts/android-status', *ROOT.glob('plugins/*/ui')]:
    if (package / 'package.json').exists():
        relative = package.relative_to(ROOT).as_posix()
        assert f'npm test --prefix {relative}' in runs, f'CI does not test {relative}'
for module in ROOT.glob('plugins/**/go.mod'):
    relative = module.parent.relative_to(ROOT).as_posix()
    assert any(job.get('defaults', {}).get('run', {}).get('working-directory') == relative
               and any('go test' in step.get('run', '') for step in job['steps'])
               for job in jobs.values()), f'CI does not test {relative}'
assert not (workflow.parent / 'validate-android-status.yml').exists()
assert not (workflow.parent / 'validate-qemu-status.yml').exists()
print('All plugin runtime suites are included in plugin test CI.')
