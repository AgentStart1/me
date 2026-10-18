"""Standard-library report utilities; copied to each independently installed plugin."""
import argparse
import functools
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


class ReportParser(argparse.ArgumentParser):
    """Resolve caller output paths, then enter one project directory for the CLI."""

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
        os.chdir(project)
        return parsed


def output_parser(cache, description, *, git_project=False):
    return ReportParser(cache, description, git_project=git_project)


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
    if os.name == 'nt':
        with open(executable, 'rb') as stream:
            shebang = stream.readline(256).strip()
        if shebang in (b'#!/bin/bash', b'#!/usr/bin/env bash'):
            return [shutil.which('bash'), executable, *args]
    return [executable, *args]


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


def serve(cache, *, git_project=False):
    """Own the loopback server and optional tunnel until cancellation or tunnel exit."""
    parser = output_parser(cache, 'Serve a report on loopback, optionally through ngrok.', git_project=git_project)
    parser.add_argument('--port', type=int, default=os.environ.get('NGROK_PORT', '8080'))
    parser.add_argument('--local-only', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Port must be an integer from 1 to 65535.')
    if not (args.output_dir / 'index.html').is_file():
        parser.error('Report site missing; generate the site first.')
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(args.output_dir.resolve()))
    tunnel = None
    previous = {}
    def stop(signum, _frame):
        raise SystemExit(128 + signum)
    with http.server.ThreadingHTTPServer(('127.0.0.1', args.port), handler) as server:
        server.daemon_threads = True
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
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
                    tunnel = subprocess.Popen(tool_command(ngrok, 'http', url, '--log=stdout'))
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
            if tunnel is not None and tunnel.poll() is None:
                tunnel.terminate()
                try:
                    tunnel.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    tunnel.kill()
                    tunnel.wait()
            server.shutdown()
            worker.join()
            for signum, original in previous.items():
                signal.signal(signum, original)
