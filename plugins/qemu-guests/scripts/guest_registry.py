"""Private per-guest discovery records shared by supervisors and read-only status."""
import hashlib
import json
import os
from pathlib import Path

from process_identity import identity, write_record


def directory():
    return Path(os.environ.get('QEMU_GUESTS_REGISTRY_DIR', Path.home() / '.qemu-guests/registry'))


def register(config, home):
    root = directory()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    identifier = hashlib.sha256(os.path.normcase(str(home.resolve())).encode()).hexdigest()[:24]
    metadata = {key: config[key] for key in ('name', 'os', 'graphical', 'memory', 'cpus', 'ssh_port')}
    metadata.update(id=identifier, state_dir=str(home.resolve()), qmp_port=config.get('qmp_port'))
    if config.get('appium'):
        metadata['appium_port'] = config['appium']['host_port']
    write_record(root / (identifier + '.json'), metadata)
    return identifier


def entries():
    root = directory()
    if not root.exists():
        return []
    result = []
    for path in sorted(root.glob('*.json'))[:64]:
        try:
            item = json.loads(path.read_text())
            if item['id'] != path.stem or not Path(item['state_dir']).is_absolute():
                continue
            result.append(item)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return result


def state(item):
    home = Path(item['state_dir'])
    try:
        record_path = home / 'running.json'
        if not record_path.exists():
            return ('recovery-required' if (home / 'session.lock').exists() else 'stopped'), None
        record = json.loads(record_path.read_text())
        if identity(record['pid']) != record['identity']:
            return 'recovery-required', None
        owner = json.loads((home / 'session.lock/owner.json').read_text())
        if owner['token'] != record['token'] or identity(owner['pid']) != owner['identity']:
            return 'recovery-required', record
        return record['phase'], record
    except (OSError, ValueError, KeyError, TypeError):
        return 'unknown', None


def snapshot():
    result = []
    for item in entries():
        phase, record = state(item)
        result.append({key: item[key] for key in ('id', 'name', 'os', 'graphical', 'memory', 'cpus', 'ssh_port')} | {
            'state': phase, 'pid': record['pid'] if record else None,
            'appiumEndpoint': f'http://127.0.0.1:{item["appium_port"]}' if item.get('appium_port') else None,
            'screenAvailable': bool(item['graphical'] and record and phase in {'booting', 'ready', 'paused'}),
            'diskPresent': (Path(item['state_dir']) / 'disk.qcow2').is_file()})
    return {'state': 'available', 'items': result}
