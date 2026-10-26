"""Private prepared-runtime manifest; no toolchain download or guest build fallback."""
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import urllib.parse
import zipfile

from guest_config import check_digest
from macos_console import text_keys


@dataclass(frozen=True)
class PermissionTarget:
    name: str
    path: str
    bundle_id: str
    cdhash: str


@dataclass(frozen=True)
class PreparedFile:
    source: Path
    name: str
    sha256: str


@dataclass(frozen=True)
class DesktopPlan:
    digest: str
    expected_build: str
    wda_url: str
    wda_service: str
    password: str = field(repr=False)
    permissions: tuple
    files: tuple
    setup_script: bytes | None
    checks: tuple


def load(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    data = json.loads(raw)
    required = {'expected_build', 'wda_url', 'wda_service', 'password_archive', 'permissions'}
    if not isinstance(data, dict) or not required <= data.keys() or data.keys() - required - {'files', 'setup_script', 'checks'}:
        raise ValueError('Invalid macOS desktop manifest fields')
    if not isinstance(data['expected_build'], str) or not re.fullmatch('[0-9A-Z]{4,16}', data['expected_build']):
        raise ValueError('An exact tested macOS build is required')
    if not isinstance(data['wda_service'], str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9.-]{1,127}', data['wda_service']):
        raise ValueError('A prepared user-domain WDA service label is required')
    if not isinstance(data['wda_url'], str):
        raise ValueError('WDA must be an existing guest loopback HTTP endpoint')
    url = urllib.parse.urlsplit(data['wda_url'])
    if url.scheme != 'http' or url.hostname != '127.0.0.1' or not url.port or url.path not in ('', '/') or url.query or url.fragment or url.username:
        raise ValueError('WDA must be an existing guest loopback HTTP endpoint')

    def local(value):
        if not isinstance(value, str) or not value or '\x00' in value:
            raise ValueError('Prepared input requires a local file path')
        return (path.parent / Path(value).expanduser()).resolve()

    for name in ('permissions', 'files', 'checks'):
        if not isinstance(data.get(name, []), list):
            raise ValueError('Prepared manifest collections require arrays')
    try:
        with zipfile.ZipFile(local(data['password_archive'])) as archive:
            if archive.getinfo('account-password').file_size > 256:
                raise ValueError('Invalid private bootstrap credential')
            password = archive.read('account-password').decode('ascii')
    except (zipfile.BadZipFile, KeyError) as error:
        raise ValueError('Invalid private bootstrap credential archive') from error
    if not password or '\n' in password or '\r' in password:
        raise ValueError('Invalid private bootstrap credential')
    text_keys(password)
    permissions = []
    for entry in data['permissions']:
        if not isinstance(entry, dict) or set(entry) != {'name', 'path', 'bundle_id', 'cdhash'}:
            raise ValueError('Permission targets require name, path, bundle_id and cdhash')
        if not all(isinstance(v, str) and v and '\x00' not in v for v in entry.values()):
            raise ValueError('Invalid permission target')
        target = PurePosixPath(entry['path'])
        if not target.is_absolute() or '..' in target.parts or not str(target).endswith('.app'):
            raise ValueError('Permission target must be an absolute application bundle')
        text_keys(entry['path'])
        if not re.fullmatch('[a-zA-Z0-9.-]+', entry['bundle_id']) or not re.fullmatch('[a-f0-9]{40,64}', entry['cdhash']):
            raise ValueError('Permission target needs its reviewed signing identity')
        permissions.append(PermissionTarget(**entry))
    if not permissions or len({p.name for p in permissions}) != len(permissions):
        raise ValueError('Permission target display names must be unique and nonempty')
    files = []
    for entry in data.get('files', []):
        if (not isinstance(entry, dict) or set(entry) != {'source', 'name', 'sha256'} or
                not all(isinstance(v, str) and v for v in entry.values()) or
                not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]*', entry['name'])):
            raise ValueError('Prepared files need source, safe basename and sha256')
        source = local(entry['source'])
        check_digest(source, entry['sha256'], 'Prepared desktop artifact')
        files.append(PreparedFile(source, entry['name'], entry['sha256']))
    if len({f.name for f in files}) != len(files):
        raise ValueError('Prepared file names collide')
    setup = local(data['setup_script']).read_bytes() if 'setup_script' in data else None
    if setup is not None and (len(setup) > 128 * 1024 or b'\x00' in setup or b'\r' in setup):
        raise ValueError('Runtime setup script must be bounded LF shell text')
    checks = []
    for entry in data.get('checks', []):
        if (not isinstance(entry, dict) or set(entry) != {'name', 'argv'} or
                not isinstance(entry['name'], str) or not re.fullmatch('[a-z0-9-]{1,64}', entry['name'])):
            raise ValueError('Invalid qualification check name')
        if not isinstance(entry['argv'], list) or not entry['argv'] or any(not isinstance(v, str) or '\x00' in v for v in entry['argv']):
            raise ValueError('Qualification checks require explicit argument arrays')
        checks.append((entry['name'], tuple(entry['argv'])))
    if len({name for name, _ in checks}) != len(checks):
        raise ValueError('Qualification check names must be unique')
    digest = hashlib.sha256(raw)
    digest.update(b'\x00credential\x00' + password.encode())
    if setup is not None:
        digest.update(b'\x00setup\x00' + setup)
    return DesktopPlan(digest.hexdigest(), data['expected_build'], data['wda_url'], data['wda_service'], password,
                       tuple(permissions), tuple(files), setup, tuple(checks))
