"""Portable project runtime requirements; provider connection details stay external."""
import hashlib
import json
from pathlib import Path
import zipfile

from guest_desktop import validate
from initialization_snapshot import InitializationSnapshot


def capture(path, system):
    path = Path(path).resolve()
    contents = path.read_bytes()
    data = json.loads(contents.decode('utf-8-sig'))
    if not isinstance(data, dict) or set(data) != {'version', 'desktop', 'platforms'} or type(data['version']) is not int or data['version'] != 1:
        raise ValueError('Runtime requirements need version:1, desktop and platforms')
    platform = {'ubuntu': 'Linux', 'windows': 'Windows'}.get(system)
    if platform is None or platform not in data['platforms']:
        raise ValueError('Runtime requirements do not support the selected guest platform')
    requirements = data['platforms'][platform]
    if not isinstance(requirements, dict) or set(requirements) - {'appium', 'java', 'packages', 'environment', 'classpath', 'hooks'}:
        raise ValueError('Unknown runtime requirement fields')
    if type(requirements.get('java')) is not int or requirements['java'] < 17:
        raise ValueError('Declare the required Java major version')
    appium = requirements.get('appium', {})
    if not isinstance(appium, dict) or set(appium) != {'version', 'drivers', 'plugins'} or not isinstance(appium['version'], str):
        raise ValueError('Declare the Appium version, drivers and plugins')
    for kind in ['drivers', 'plugins']:
        if not isinstance(appium[kind], dict) or any(not isinstance(k, str) or not isinstance(v, str) for k,v in appium[kind].items()):
            raise ValueError('Appium extensions require name/version mappings')
    for field in ['environment', 'classpath']:
        values = requirements.get(field, [])
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            raise ValueError('Runtime environment/classpath requirements must be string lists')
    desktop = validate({**data['desktop'], 'packages': requirements.get('packages', [])}, system, True)
    from project_setup_hooks import validate as validate_hooks
    hooks = validate_hooks(requirements.get('hooks', {}), path.parent)
    guest_files = tuple((f'project-setup-{index}' + Path(item['script']).suffix,
                         Path(item['script']).read_bytes()) for index, item in enumerate(hooks['guest_setup']))
    staged_hooks = [{**item, 'script': guest_files[index][0]} for index, item in enumerate(hooks['guest_setup'])]
    digest = hashlib.sha256(contents)
    if guest_files:
        scripts = [{'script': requirements['hooks']['guest_setup'][index]['script'],
                    'sha256': hashlib.sha256(body).hexdigest()}
                   for index, (_name, body) in enumerate(guest_files)]
        digest.update(json.dumps({'guest_scripts_v2': scripts}, sort_keys=True, separators=(',', ':')).encode())
    record = {'desktop': desktop, 'runtime': requirements, 'hooks': hooks, 'sha256': digest.hexdigest()}
    return InitializationSnapshot(contents, json.dumps(record).encode(), guest_files, json.dumps(staged_hooks).encode())


def load(path, system):
    return capture(path, system).record()


def apply(config, path):
    result = {**config}
    snapshot = capture(path, config['os'])
    requirements = snapshot.record()
    if not config['graphical']:
        raise ValueError('Desktop runtime requirements require a graphical guest')
    result['desktop'] = requirements['desktop']
    result['runtime_requirements'] = requirements
    result['initialization_snapshot'] = snapshot
    return result


def _verify_target(manifest, system):
    platform = {'ubuntu': 'linux', 'windows': 'win32', 'macos': 'darwin'}.get(system)
    if platform is not None and (manifest.get('platform') != platform or manifest.get('arch') != 'x64'):
        raise ValueError(f'Prepared runtime target must be {platform}/x64')


def verify_runtime_target(archive_path, system):
    with zipfile.ZipFile(archive_path) as archive:
        _verify_target(json.loads(archive.read('runtime.json')), system)


def verify_runtime(archive_path, requirements, system):
    with zipfile.ZipFile(archive_path) as archive:
        manifest = json.loads(archive.read('runtime.json'))
        _verify_target(manifest, system)
        if manifest['appium'] != requirements['runtime']['appium']['version']:
            raise ValueError('Prepared runtime does not match the project Appium version')
        inventory = manifest.get('extensions', {})
        for kind in ['drivers', 'plugins']:
            for name, version in requirements['runtime']['appium'][kind].items():
                if inventory.get(kind, {}).get(name) != version:
                    raise ValueError('Prepared runtime is missing a required Appium extension/version')
        if requirements['desktop'] and manifest['platform'] == 'win32' and 'desktop-helper.dll' not in archive.namelist():
            raise ValueError('Prepare the desktop helper on the host')
        for name in requirements['runtime'].get('environment', []):
            if name not in manifest.get('environment', {}):
                raise ValueError('Prepared runtime is missing a required environment dependency')
        for coordinate in requirements['runtime'].get('classpath', []):
            if coordinate not in manifest.get('classpath', {}):
                raise ValueError('Prepared runtime is missing a required prebuilt native classpath dependency')
