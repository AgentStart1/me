"""Declarative host-test environments, independent of applications and frameworks."""
import json
import os
from pathlib import Path
import re


def host_path(value, base):
    if not isinstance(value, str):
        raise ValueError('Expected a path string')
    value = os.path.expandvars(value)
    if re.search(r'\$\{[^}]+\}', value):
        raise ValueError('Test environment path contains an unset environment variable')
    if os.name == 'nt' and re.match(r'^/[a-zA-Z]/', value):
        value = value[1] + ':' + value[2:]
    path = Path(value).expanduser()
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def load(path):
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict) or set(data) - {'version', 'workspace', 'docker', 'appium', 'environment', 'requirements'}:
        raise ValueError('Unknown test environment fields')
    if type(data.get('version')) is not int or data['version'] != 1:
        raise ValueError('Test environment requires version: 1')
    workspace = host_path(data.get('workspace', '.'), path.parent)
    environment = data.get('environment', {})
    if not isinstance(environment, dict) or any(not isinstance(k, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', k)
                                              or not isinstance(v, str) or '\0' in v
                                              for k, v in environment.items()):
        raise ValueError('environment must contain string values')
    result = {'workspace': workspace, 'environment': environment}
    if 'requirements' in data:
        result['requirements'] = host_path(data['requirements'], path.parent)
    if 'docker' not in data and os.environ.get('TEST_ENV_DOCKER_PROFILE'):
        data['docker'] = {'profile': os.environ['TEST_ENV_DOCKER_PROFILE']}
    if 'docker' in data:
        docker = data['docker']
        if not isinstance(docker, dict) or set(docker) != {'profile'}:
            raise ValueError('docker requires profile')
        result['docker'] = host_path(docker['profile'], workspace)
    if 'appium' in data:
        appium = data['appium']
        if isinstance(appium, dict) and 'guest' not in appium and os.environ.get('TEST_ENV_GUEST_PROFILE'):
            appium['guest'] = os.environ['TEST_ENV_GUEST_PROFILE']
        if not isinstance(appium, dict) or set(appium) != {'guest', 'launch', 'cleanup_roots'}:
            raise ValueError('appium requires guest, launch and cleanup_roots')
        launch = appium['launch']
        fields = {'kind', 'inputs', 'outputs', 'directories', 'services'}
        if not isinstance(launch, dict) or set(launch) - {'artifacts'} != fields or launch['kind'] != 'java-argfile':
            raise ValueError('Only the explicit java-argfile launch adapter is supported')
        for key in (fields | (set(launch) & {'artifacts'})) - {'kind'}:
            if not isinstance(launch[key], list) or any(not isinstance(v, str) or not re.fullmatch(r'[\w.-]+', v)
                                                       for v in launch[key]):
                raise ValueError(f'launch.{key} must contain JVM property names')
        roots = appium['cleanup_roots']
        if not isinstance(roots, list) or not roots:
            raise ValueError('Declare private cleanup roots explicitly')
        resolved = [host_path(root, workspace) for root in roots]
        if any(root == workspace or workspace not in root.parents for root in resolved):
            raise ValueError('Cleanup roots must be strictly inside the workspace')
        result['appium'] = {'guest': host_path(appium['guest'], workspace),
                            'launch': launch, 'cleanup_roots': resolved}
    return result
