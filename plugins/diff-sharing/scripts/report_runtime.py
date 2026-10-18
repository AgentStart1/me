"""Standard-library report utilities; copied to each independently installed plugin."""
import argparse
import functools
from contextlib import contextmanager
import tempfile
import uuid
import re
import hashlib
import http.server
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
from datetime import datetime, timezone
from command_tree import CommandTree, script_command


class ReportParser(argparse.ArgumentParser):
    """Resolve explicit project and caller-relative output paths without changing cwd."""

    def __init__(self, cache, description, *, git_project):
        super().__init__(description=description)
        self.cache = cache
        self.git_project = git_project
        self.add_argument('--output-dir', type=Path, default=os.environ.get('REPORT_OUTPUT_DIR') or None)
        if not git_project:
            self.add_argument('--project-dir', type=Path, default=Path.cwd(),
                              help='Project directory for report searches and cache identity (default: current directory).')

    def parse_args(self, args=None, namespace=None):
        parsed = super().parse_args(args, namespace)
        if self.git_project:
            root = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], stderr=subprocess.PIPE)
            project = Path(os.fsdecode(root.rstrip(b'\r\n'))).resolve()
        else:
            project = parsed.project_dir.resolve()
        if not project.is_dir():
            self.error(f'Project directory does not exist or is not a directory: {project}')
        if parsed.output_dir is None:
            digest = hashlib.md5(str(project).encode()).hexdigest()
            parsed.output_dir = Path.home() / '.cache' / self.cache / digest
        else:
            parsed.output_dir = parsed.output_dir.resolve()
        parsed.project_dir = project
        return parsed


def output_parser(cache, description, *, git_project=False):
    return ReportParser(cache, description, git_project=git_project)


def current_generation(output):
    """Resolve one published snapshot; old flat caches remain readable."""
    pointer = output / 'current.json'
    if not pointer.exists():
        return output
    record = json.loads(pointer.read_text(encoding='utf-8'))
    generation = record.get('generation') if isinstance(record, dict) else None
    if not isinstance(generation, str) or not re.fullmatch('[a-f0-9]{32}', generation):
        raise ValueError('Invalid report snapshot pointer')
    result = output / 'generations' / generation
    if not result.is_dir():
        raise ValueError('Published report snapshot is missing')
    return result


def atomic_json(path, value):
    descriptor, name = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def report_snapshot(output):
    """Build privately, then publish one complete generation with an atomic pointer.

    Existing generations are retained so open pages and pinned URLs keep their assets.
    Yield (staging_path, published_path); the published path is valid after success.
    Failed builds never change the current pointer. Last completed publication wins.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    generations = output / 'generations'
    identifier = uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix='.building-', dir=output.parent) as directory:
        staged = Path(directory) / 'site'
        staged.mkdir()
        yield staged, generations / identifier
        if not (staged / 'index.html').is_file():
            raise ValueError('Snapshot has no complete site index')
        generations.mkdir(parents=True, exist_ok=True)
        os.replace(staged, generations / identifier)
        atomic_json(output / 'current.json', {'generation': identifier})


def materialize_tree(source, destination, *, ignore=None, dirs_exist_ok=False):
    """Freeze linked asset bytes too, rejecting directory cycles before copying them."""
    def bounded_ignore(directory, names):
        try:
            excluded = set(ignore(directory, names) if ignore else ())
            ancestors = {parent.resolve() for parent in (Path(directory), *Path(directory).parents)}
            for name in names:
                item = Path(directory) / name
                if name not in excluded and item.is_dir() and item.resolve() in ancestors:
                    raise ValueError('Cyclic directory link in report assets')
            return excluded
        except RuntimeError as error:
            raise ValueError('Unresolvable directory link in report assets') from error
    shutil.copytree(source, destination, symlinks=False, dirs_exist_ok=dirs_exist_ok, ignore=bounded_ignore)


def ensure_site(output, assemble):
    """Reuse a complete immutable site, or publish one migration from a flat cache."""
    source = current_generation(output)
    if source != output:
        if not (source / 'index.html').is_file():
            raise ValueError('Published report index is missing; regenerate the snapshot')
        return source
    with report_snapshot(output) as (staged, published):
        if source.is_dir():
            def ignore(directory, names):
                if Path(directory) != source or source != output:
                    return []
                generated = {'diff', 'reports', 'test-results', 'index.html', 'style.css'}
                return [name for name in names if name not in generated]
            materialize_tree(source, staged, dirs_exist_ok=True, ignore=ignore)
        assemble(staged)
    return published


@contextmanager
def protected_cleanup():
    numbers = [signal.SIGINT, signal.SIGTERM] + ([signal.SIGBREAK] if hasattr(signal, 'SIGBREAK') else [])
    previous = {number: signal.signal(number, signal.SIG_IGN) for number in numbers}
    try:
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def timestamp():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def find_tool(name):
    # Windows PATH lookup normally excludes extensionless Bash tools.
    for directory in os.get_exec_path():
        found = shutil.which(name, path=directory)
        if found:
            return found
        candidate = Path(directory) / name
        if candidate.is_file() and (os.name == 'nt' or os.access(candidate, os.X_OK)):
            return str(candidate.resolve())
    return None


def tool_command(executable, *args):
    return script_command(executable, *args)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def render(template, values):
    import re
    text = template.read_text(encoding='utf-8')
    text = re.sub(r'<!-- (@@[A-Z_]+@@) -->', r'\1', text)
    return re.sub(r'@@([A-Z_]+)@@', lambda match: str(values[match[1]]),
                  text)


def run_cli(action):
    try:
        action()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'Error: {error}') from error


@contextmanager
def running_server(port, handler):
    """Own the listening socket and serving thread as one resource."""
    with http.server.ThreadingHTTPServer(('127.0.0.1', port), handler) as server:
        server.daemon_threads = True
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield worker
        finally:
            with protected_cleanup():
                server.shutdown()
                worker.join()


def serve(cache, *, git_project=False):
    """Own the loopback server and optional tunnel until cancellation or tunnel exit."""
    parser = output_parser(cache, 'Serve a report on loopback, optionally through ngrok.', git_project=git_project)
    parser.add_argument('--port', type=int, default=os.environ.get('NGROK_PORT', '8080'))
    parser.add_argument('--local-only', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Port must be an integer from 1 to 65535.')
    if not (current_generation(args.output_dir) / 'index.html').is_file():
        parser.error('Report site missing; generate the site first.')
    class SnapshotHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path.split('?', 1)[0] in ('/', '/index.html'):
                generation = current_generation(args.output_dir)
                if generation != args.output_dir:
                    self.send_response(302)
                    self.send_header('Location', '/' + generation.relative_to(args.output_dir).as_posix() + '/index.html')
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    return
            super().do_GET()
    handler = functools.partial(SnapshotHandler, directory=str(args.output_dir.resolve()))
    tunnel = None
    previous = {}
    def stop(signum, _frame):
        raise SystemExit(128 + signum)
    tree = CommandTree()
    with running_server(args.port, handler) as worker:
        try:
            signals = (signal.SIGINT, signal.SIGTERM)
            if os.name == 'nt':
                signals += (signal.SIGBREAK,)
            for signum in signals:
                previous[signum] = signal.signal(signum, stop)
            url = f'http://127.0.0.1:{args.port}'
            print(f'Local report: {url}', flush=True)
            print('Press Ctrl+C to stop this report server.', flush=True)
            ngrok = find_tool('ngrok')
            if not args.local_only and ngrok:
                try:
                    tunnel = tree.start(tool_command(ngrok, 'http', url, '--log=stdout'))
                except OSError:
                    print('ngrok could not launch.', flush=True)
                if tunnel is not None:
                    while tunnel.poll() is None:
                        worker.join(timeout=0.2)
                    if tunnel.returncode == 0:
                        return
                print('ngrok could not start; the loopback report remains available.', flush=True)
            elif not args.local_only:
                print('ngrok is unavailable; the loopback report remains available.', flush=True)
            while worker.is_alive():
                worker.join(timeout=0.2)
        finally:
            # Repeated cancellation cannot interrupt tree shutdown or socket cleanup.
            for signum in previous:
                signal.signal(signum, signal.SIG_IGN)
            try:
                tree.stop()
            finally:
                for signum, original in previous.items():
                    signal.signal(signum, original)
