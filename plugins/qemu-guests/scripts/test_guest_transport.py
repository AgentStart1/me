"""Owned, bounded OpenSSH transport. Transfers artifacts; never compiles in guests."""
import base64
from contextlib import nullcontext
from pathlib import Path
import subprocess
import time
import threading
import zipfile
from resource_ownership import Cancelled, defer_cancellation
from test_cancellation import current_cancellation
from test_environment_owner import CleanupUncertain


class TransportCleanupError(CleanupUncertain):
    """All child stops were attempted; failures retains each original exception."""

    def __init__(self, failures):
        self.failures = tuple(failures)
        super().__init__(f'Guest transport failed to stop {len(self.failures)} owned child process(es)')


def quote(path):
    return "'" + str(path).replace("'", "''") + "'"


class GuestTransport:
    def __init__(self, config, temporary):
        self.target = config['ssh_user'] + '@127.0.0.1'
        self.key = config['access_key']
        self.port = str(config['ssh_port'])
        self.temporary = Path(temporary)
        self.children = []
        self.serial = 0
        self.cancellation = current_cancellation()
        known_hosts = Path(config['state_dir']) / 'known_hosts' if config.get('state_dir') else None
        self.host_keys = ['-o', 'UserKnownHostsFile=' + str(known_hosts), '-o', 'StrictHostKeyChecking=yes'] if known_hosts and known_hosts.exists() else []

    def ssh(self):
        return ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
                '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
                '-i', self.key, '-p', self.port, *self.host_keys]

    def run(self, command, timeout=180, operation='SSH command', stdin_data=None):
        with self.cancellation.worker() if self.cancellation is not None else nullcontext():
            result = (self._run_cancellable(command, timeout, stdin_data) if self.cancellation is not None
                      else subprocess.run(command, input=stdin_data, capture_output=True, timeout=timeout))
            if result.returncode:
                # Commands and output can contain credentials; do not echo them.
                (self.temporary.parent / 'transport-error.log').write_bytes(result.stdout + result.stderr)
                raise RuntimeError(f'Guest {operation} failed (exit {result.returncode}); inspect private transport-error.log')
            return result.stdout

    def _run_cancellable(self, command, timeout, stdin_data):
        self.cancellation.checkpoint()
        # This child is owned before the next checkpoint, including constructor
        # preflight calls made before the transport itself is registered.
        with defer_cancellation() if threading.current_thread() is threading.main_thread() else nullcontext():
            child = subprocess.Popen(command, stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.children.append(child)
        deadline = time.monotonic() + timeout
        payload = stdin_data
        try:
            while True:
                self.cancellation.checkpoint()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                try:
                    stdout, stderr = child.communicate(input=payload, timeout=min(.1, remaining))
                    return subprocess.CompletedProcess(command, child.returncode, stdout, stderr)
                except subprocess.TimeoutExpired:
                    payload = None
        except BaseException as error:
            self.cancellation.observe(error)
            raise
        finally:
            try:
                self.stop(child)
                self.children.remove(child)
            except BaseException as error:
                self.cancellation.observe(error)
                raise TransportCleanupError([error]) from error

    @staticmethod
    def encoded(script):
        script = "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; " + script
        return 'powershell.exe -NoProfile -EncodedCommand ' + base64.b64encode(script.encode('utf-16le')).decode()

    def powershell(self, script):
        # Windows OpenSSH may invoke cmd.exe, whose command-line limit is much
        # shorter than a suite's accumulated artifact paths. Keep the remote
        # command fixed-size; transport the script as UTF-8 data, not arguments.
        # PowerShell's stdin command mode consumes the complete line directly.
        # An encoded payload keeps script text independent of console codepages.
        payload = base64.b64encode(script.encode('utf-8')).decode('ascii')
        bootstrap = ("$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; $LASTEXITCODE=$null; "
                     "try { & ([scriptblock]::Create([Text.Encoding]::UTF8.GetString("
                     "[Convert]::FromBase64String('" + payload + "')))) } "
                     "catch { Write-Error $_ -ErrorAction Continue; exit 1 }; "
                     "if ($null -ne $LASTEXITCODE) { exit $LASTEXITCODE }; exit 0\r\n")
        return self.run([*self.ssh(), '-T', self.target,
                         'powershell.exe -NoProfile -NonInteractive -Command -'],
                        stdin_data=bootstrap.encode('ascii'))

    def scp(self):
        return ['scp', '-q', '-o', 'BatchMode=yes', '-P', self.port, '-i', self.key, *self.host_keys]

    def mkdir(self, paths):
        paths = sorted(set(str(p) for p in paths))
        if paths:
            self.powershell('New-Item -ItemType Directory -Force -Path ' + ','.join(map(quote, paths)) + ' | Out-Null')

    def upload(self, source, destination=None):
        destination = destination or source
        self.run([*self.scp(), str(source), self.target + ':' + str(destination).replace('\\', '/')], operation='artifact upload')

    def download(self, source):
        path = Path(source)
        exists = self.powershell('if (Test-Path -LiteralPath ' + quote(source) + ') { Write-Output YES }')
        if exists.strip() != b'YES':
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        self.run([*self.scp(), self.target + ':' + str(source).replace('\\', '/'), str(path)])

    def remove_files(self, paths):
        if paths:
            self.powershell('foreach ($path in @(' + ','.join(map(quote, paths)) +
                            ')) { if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force } }')

    def remove_private_directory(self, path, roots):
        path = Path(path).resolve()
        if not any(root in path.parents for root in roots):
            raise ValueError('Refusing cleanup outside the declared private roots')
        self.powershell('if (Test-Path -LiteralPath ' + quote(path) + ') { Remove-Item -LiteralPath ' +
                        quote(path) + ' -Recurse -Force }')

    def stage(self, files):
        if not files:
            return
        archive = self.temporary / 'runtime.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as output:
            for source in files:
                source = Path(source).resolve()
                if source.drive.upper() != 'C:':
                    raise ValueError('Transparent Windows artifacts currently require C: paths')
                if {p.lower() for p in source.parts} & {'secrets', '.ssh', '.git'} or source.suffix.lower() in {'.pem', '.key'}:
                    raise ValueError('Refusing a private credential in a runtime archive')
                output.write(source, source.as_posix()[3:])
        self.mkdir(['C:/ProgramData/qemu-guests/test-transfers'])
        destination = 'C:/ProgramData/qemu-guests/test-transfers/' + self.temporary.name + '.zip'
        try:
            self.upload(archive, destination)
            self.powershell('tar.exe -xf ' + quote(destination) + " -C C:/; if ($LASTEXITCODE -ne 0) { throw 'Artifact extraction failed' }")
        finally:
            archive.unlink(missing_ok=True)
            self.remove_files([destination])

    def forward(self, options):
        with self.cancellation.worker() if self.cancellation is not None else nullcontext():
            return self._forward(options)

    def _forward(self, options):
        self.serial += 1
        log = self.temporary / f'forward-{self.serial}.log'
        error = self.temporary / f'forward-{self.serial}.err'
        # No remote command: Windows OpenSSH can orphan a shell blocked in ReadToEnd.
        command = [*self.ssh(), '-N', '-T', '-v', '-o', 'ExitOnForwardFailure=yes', *options, self.target]
        # Signal delivery is deferred only on the main thread. HTTP workers are
        # joined through the proxy lock before transport cleanup can proceed.
        handoff = defer_cancellation() if threading.current_thread() is threading.main_thread() else nullcontext()
        with handoff:
            with log.open('wb') as out, error.open('wb') as err:
                child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
            self.children.append(child)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and child.poll() is None:
            if self.cancellation is not None:
                self.cancellation.checkpoint()
            if error.exists():
                progress = error.read_bytes()
                local_ready = progress.count(b'Local forwarding listening on ') >= options.count('-L')
                remote_ready = progress.count(b'remote forward success for:') >= options.count('-R')
                if b'Entering interactive session.' in progress and local_ready and remote_ready:
                    return child
            time.sleep(.1)
        self.stop(child)
        self.children.remove(child)
        raise RuntimeError('Guest forwarding failed; no local execution fallback is permitted')

    def stop(self, child):
        with self.cancellation.worker() if self.cancellation is not None else nullcontext():
            try:
                self._stop(child)
            except BaseException as error:
                if self.cancellation is not None:
                    self.cancellation.report_cleanup(error)
                    self.cancellation.observe(error)
                raise

    @staticmethod
    def _stop(child):
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        if child.stdin:
            child.stdin.close()
        for name in ('stdout', 'stderr'):
            stream = getattr(child, name, None)
            if stream is not None:
                stream.close()

    def close(self):
        """Attempt every owned child in reverse order before reporting failures.

        Preserve cancellation identity after draining cleanup. Keep child handles
        for inspection/retry; only the environment owner may release the lease.
        """
        cancellation = getattr(self, 'cancellation', None)
        if cancellation is not None:
            cancellation.require_main_thread()
        failures = []
        for child in reversed(self.children):
            try:
                self.stop(child)
            except BaseException as error:
                failures.append(error)
        if failures:
            aggregate = TransportCleanupError(failures)
            cancellation = next((error for error in failures
                                 if isinstance(error, Cancelled) or not isinstance(error, Exception)), None)
            if cancellation is not None:
                raise cancellation from aggregate
            raise aggregate from failures[0]
