"""POSIX runtime transport for host-built JVM applications; no guest build commands."""
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import tarfile

from test_guest_transport import GuestTransport


class LinuxTransport(GuestTransport):
    def __init__(self, config, temporary, runtime=None):
        super().__init__(config, temporary)
        self.guest_classpath = []
        if runtime:
            data = json.loads(Path(runtime).read_text(encoding='utf-8-sig'))
        else:
            metadata = self.shell("python3 -c 'import json; print(json.dumps(json.load(open(\"/opt/qemu-guests/appium/runtime.json\")).get(\"classpath\", {})))'")
            dependencies = json.loads(metadata)
            for relative in dependencies.values():
                path = PurePosixPath(relative)
                if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != 'assets':
                    raise ValueError('Prepared guest runtime contains an unsafe classpath entry')
                self.guest_classpath.append('/opt/qemu-guests/appium/' + str(path))
            data = {'root': '/home/' + config['ssh_user'] + '/.local/share/test-environments/runtime',
                    'java': '/usr/bin/java', 'classpath': []}
        if set(data) - {'appium_port'} != {'root', 'java', 'classpath'}:
            raise ValueError('Linux runtime requires root, java and prebuilt classpath')
        for key in ('root', 'java'):
            value = data[key]
            if not isinstance(value, str) or not value.startswith('/') or '..' in PurePosixPath(value).parts or '\0' in value:
                raise ValueError('Linux runtime paths must be absolute, normalized POSIX paths')
        self.root = PurePosixPath(data['root'])
        if len(self.root.parts) < 4:
            raise ValueError('Linux runtime root must be a dedicated directory below the user home or runtime storage')
        self.java = data['java']
        self.appium_port = data.get('appium_port', 4723)
        if type(self.appium_port) is not int or not 1024 <= self.appium_port <= 65535:
            raise ValueError('Linux runtime appium_port must be in 1024..65535')
        if not isinstance(data['classpath'], list) or any(not isinstance(p, str) for p in data['classpath']):
            raise ValueError('Linux runtime classpath must list prebuilt host files')
        self.classpath = [Path(p).resolve() for p in data['classpath']]
        if any(not p.is_file() for p in self.classpath):
            raise ValueError('A prebuilt Linux runtime classpath file is missing')

    def shell(self, script, data=None):
        if data is not None:
            return self.run([*self.ssh(), '-T', self.target, script], stdin_data=data)
        return self.run([*self.ssh(), '-T', self.target, 'sh -eu -s'], stdin_data=script.encode())

    def mapped(self, path):
        source = Path(path).resolve()
        if source.drive:
            relative = source.drive.rstrip(':').upper() + '/' + source.as_posix()[3:]
        else:
            relative = 'posix/' + source.as_posix().lstrip('/')
        return str(self.root / relative)

    def mkdir(self, paths):
        if paths:
            self.shell('mkdir -p -- ' + ' '.join(shlex.quote(self.mapped(p)) for p in paths))

    def upload(self, source, destination=None):
        self.run([*self.scp(), str(source), self.target + ':' + (destination or self.mapped(source))], operation='artifact upload')

    def download(self, source):
        remote = shlex.quote(self.mapped(source))
        exists = self.shell('if test -f ' + remote + '; then printf YES; fi')
        if exists != b'YES':
            return
        Path(source).parent.mkdir(parents=True, exist_ok=True)
        self.run([*self.scp(), self.target + ':' + self.mapped(source), str(source)], operation='output download')

    def remove_files(self, paths):
        if paths:
            self.shell('rm -f -- ' + ' '.join(shlex.quote(self.mapped(p)) for p in paths))

    def remove_private_directory(self, path, roots):
        path = Path(path).resolve()
        if not any(root in path.parents for root in roots):
            raise ValueError('Refusing cleanup outside the declared private roots')
        self.shell('rm -rf -- ' + shlex.quote(self.mapped(path)))

    def stage(self, files):
        if not files:
            return
        archive = self.temporary / 'runtime.tar.gz'
        try:
            with tarfile.open(archive, 'w:gz') as output:
                for source in files:
                    source = Path(source).resolve()
                    if {p.lower() for p in source.parts} & {'secrets', '.ssh', '.git'} or source.suffix.lower() in {'.pem', '.key'}:
                        raise ValueError('Refusing a private credential in a runtime archive')
                    info = output.gettarinfo(str(source), arcname=str(PurePosixPath(self.mapped(source)).relative_to(self.root)))
                    if not info.isfile():
                        raise ValueError('Runtime archive accepts regular files only')
                    info.mode = 0o644
                    with source.open('rb') as content:
                        output.addfile(info, content)
            self.shell('mkdir -p -- ' + shlex.quote(str(self.root)))
            self.shell('tar -xzf - -C ' + shlex.quote(str(self.root)), archive.read_bytes())
        finally:
            archive.unlink(missing_ok=True)

    def upload_arguments(self, argument_file, values, roles, capabilities):
        mapped = []
        index = 0
        path_roles = set(roles['inputs'] + roles['outputs'] + roles['directories'] + roles.get('artifacts', []))
        while index < len(values):
            value = values[index]
            if value in {'-cp', '-classpath', '--class-path'}:
                index += 1
                paths = [self.mapped(p) for p in values[index].split(os.pathsep)]
                mapped.extend([value, ':'.join([*paths, *(self.mapped(p) for p in self.classpath), *self.guest_classpath])])
            elif value.startswith('-D') and '=' in value and value[2:].split('=', 1)[0] in path_roles:
                name, path = value.split('=', 1)
                mapped.append(name + '=' + self.mapped(path))
            elif value.startswith('-XX:ErrorFile='):
                mapped.append('-XX:ErrorFile=' + self.mapped(value.split('=', 1)[1]))
            elif value.startswith('-javaagent:'):
                path, separator, options = value[len('-javaagent:'):].partition('=')
                mapped.append('-javaagent:' + self.mapped(path) + (separator + options if separator else ''))
            else:
                mapped.append(value)
            index += 1
        payload = ''.join(json.dumps(value, ensure_ascii=False) + '\n' for value in mapped).encode()
        # The shell command contains only the quoted destination; argument text stays stdin data.
        self.shell('cat > ' + shlex.quote(self.mapped(argument_file)), payload)
        self.shell('test -x ' + shlex.quote(self.java))
        return {**capabilities, 'appium:app': self.java,
                'appium:appArguments': ['@' + self.mapped(argument_file)],
                'appium:appWorkingDir': self.mapped(capabilities.get('appium:appWorkingDir', argument_file.parent))}
