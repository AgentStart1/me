"""Map explicit JVM launch-property roles onto artifact, file and service transport."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


def arguments(capabilities):
    value = capabilities.get('appium:appArguments', '')
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    if not isinstance(value, str):
        raise ValueError('Configured Java proxy requires one JVM argument-file capability')
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    if not value.startswith('@') or '\n' in value:
        raise ValueError('Configured Java proxy requires one JVM argument-file capability')
    path = Path(value[1:]).resolve()
    # Java argument-file syntax emitted by clients may quote/escape each argument.
    # Deliberately reject arbitrary shell syntax instead of evaluating it.
    values = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if any(not isinstance(value, str) for value in values):
        raise ValueError('JVM argument file must contain quoted string arguments')
    return path, values


def properties(values):
    return dict(value[2:].split('=', 1) for value in values if value.startswith('-D') and '=' in value)


def service_ports(values, names):
    result = set()
    for name in names:
        if name not in values:
            continue
        url = urlsplit(values[name])
        if url.scheme not in {'http', 'https', 'ws', 'wss'}:
            raise ValueError('Configured service property must be an HTTP/WebSocket URL')
        if url.hostname in {'localhost', '127.0.0.1', '::1'}:
            port = url.port or (443 if url.scheme in {'https', 'wss'} else 80)
            result.add(port)
    return sorted(result)


def artifact_files(capabilities, values, include_runtime=True):
    paths = []
    executable = Path(capabilities['appium:app']).resolve()
    if executable.name.lower() not in {'java', 'java.exe', 'javaw.exe'}:
        raise ValueError('Java launch proxy requires an existing host Java executable')
    if include_runtime:
        paths.append(executable.parent.parent)
    for index, value in enumerate(values):
        if value in {'-cp', '-classpath', '--class-path'}:
            paths.extend(Path(item) for item in values[index + 1].split(os.pathsep))
        elif value.startswith('-javaagent:'):
            paths.append(Path(value[len('-javaagent:'):].split('=', 1)[0]))
    result = set()
    for path in paths:
        if path.is_file():
            result.add(path.resolve())
        elif path.is_dir():
            result.update(item.resolve() for item in path.rglob('*') if item.is_file())
        elif path == executable.parent.parent:
            raise ValueError('Host Java runtime is missing; compiling/installing it in the work VM is not permitted')
        # Empty Gradle resource directories can be absent from an otherwise valid classpath.
    return sorted(result)


class JavaLaunch:
    def __init__(self, transport, config, workspace):
        self.transport = transport
        self.config = config
        self.workspace = workspace
        self.uploaded = {}
        self.outputs = set()
        self.argument_files = set()
        self.private = set()
        self.forwarding = None

    def prepare(self, capabilities):
        self.stop_forwarding()
        argument_file, values = arguments(capabilities)
        if self.workspace not in argument_file.parents:
            raise ValueError('JVM launch files must stay inside the host test workspace')
        self.argument_files.add(argument_file)
        props = properties(values)
        roles = self.config['launch']
        artifacts = [Path(props[name]).resolve() for name in roles.get('artifacts', []) if name in props]
        inputs = [Path(props[name]).resolve() for name in roles['inputs'] if name in props]
        outputs = [Path(props[name]).resolve() for name in roles['outputs'] if name in props]
        if any(self.workspace not in path.parents for path in outputs):
            raise ValueError('Proxy outputs must stay inside the host test workspace')
        self.outputs.update(outputs)
        directories = [Path(props[name]).resolve() for name in roles['directories'] if name in props]
        directories += [path.parent for path in [argument_file, *inputs, *self.outputs]]
        directories += [Path(capabilities.get('appium:appWorkingDir', self.workspace)).resolve()]
        for path in inputs:
            for root in self.config['cleanup_roots']:
                if root in path.parents:
                    relative = path.relative_to(root)
                    if len(relative.parts) < 2:
                        raise ValueError('Private input requires a per-case directory under its cleanup root')
                    self.private.add(root / relative.parts[0])
                    break
            else:
                raise ValueError('Private input is outside the declared cleanup roots')
        self.transport.mkdir(directories)
        changed = []
        signatures = {}
        linux = hasattr(self.transport, 'upload_arguments')
        runtime_files = artifact_files(capabilities, values, include_runtime=False) if linux else artifact_files(capabilities, values)
        for path in [*runtime_files, *artifacts, *getattr(self.transport, 'classpath', [])]:
            stat = path.stat()
            signature = (stat.st_size, stat.st_mtime_ns)
            signatures[path] = signature
            if self.uploaded.get(path) != signature:
                changed.append(path)
        self.transport.stage(changed)
        self.uploaded.update(signatures)
        if linux:
            capabilities = self.transport.upload_arguments(argument_file, values, roles, capabilities)
        else:
            self.transport.upload(argument_file)
        for path in inputs:
            if path.is_file():
                self.transport.upload(path)
            else:
                self.transport.remove_files([path])
        options = []
        for port in service_ports(props, roles['services']):
            options += ['-R', f'127.0.0.1:{port}:127.0.0.1:{port}']
        if options:
            self.forwarding = self.transport.forward(options)
        return capabilities

    def collect(self):
        for path in sorted(self.outputs):
            # A test report can already have removed an earlier case's private parent.
            if path.parent.exists():
                self.transport.download(path)

    def stop_forwarding(self):
        if self.forwarding:
            self.transport.stop(self.forwarding)
            self.forwarding = None

    def close(self):
        self.stop_forwarding()
        for path in sorted(self.private):
            self.transport.remove_private_directory(path, self.config['cleanup_roots'])
        if self.argument_files:
            self.transport.remove_files(sorted(self.argument_files))
