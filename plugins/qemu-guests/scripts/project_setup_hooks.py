"""Project-owned foreground setup hooks; compilation belongs only to host hooks."""
from pathlib import Path
import os
import subprocess
from command_tree import CommandTree


def validate(value, base):
    if not isinstance(value, dict) or set(value) - {'host_prepare', 'guest_setup'}:
        raise ValueError('hooks accepts host_prepare and guest_setup')
    result = {'host_prepare': [], 'guest_setup': []}
    for kind in result:
        hooks = value.get(kind, [])
        if not isinstance(hooks, list):
            raise ValueError('Setup hooks must be lists')
        for item in hooks:
            fields = {'command', 'cwd', 'timeout_seconds'} if kind == 'host_prepare' else {'script', 'interpreter', 'arguments', 'timeout_seconds'}
            if not isinstance(item, dict) or set(item) != fields:
                raise ValueError('Setup hooks require explicit command/script, arguments and timeout')
            timeout = item['timeout_seconds']
            if type(timeout) is not int or not 1 <= timeout <= 3600:
                raise ValueError('Hook timeout must be in 1..3600 seconds')
            args = item['command'] if kind == 'host_prepare' else item['arguments']
            if not isinstance(args, list) or any(not isinstance(v, str) or '\0' in v for v in args):
                raise ValueError('Hook arguments must be strings')
            if kind == 'host_prepare':
                if not args:
                    raise ValueError('Host preparation needs a command')
                result[kind].append({**item, 'cwd': str((base / item['cwd']).resolve())})
            else:
                path = (base / item['script']).resolve()
                if item['interpreter'] not in {'bash', 'powershell', 'python3'} or not path.is_file() or path.suffix.lower() not in {'.sh', '.ps1', '.py'}:
                    raise ValueError('Guest setup needs an existing shell/PowerShell/Python script')
                result[kind].append({**item, 'script': str(path)})
    return result


def prepare_host(hooks, log_directory):
    log_directory = Path(log_directory)
    log_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    for index, item in enumerate(hooks):
        descriptor = os.open(log_directory / f'host-prepare-{index}.log', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, 'wb') as log:
            tree = CommandTree()
            try:
                child = tree.start(item['command'], cwd=item['cwd'], stdout=log, stderr=subprocess.STDOUT)
                if child.wait(timeout=item['timeout_seconds']) != 0:
                    raise RuntimeError('Host preparation hook failed; inspect private preparation logs')
            except subprocess.TimeoutExpired:
                raise RuntimeError('Host preparation hook timed out; inspect private preparation logs') from None
            finally:
                tree.stop()
