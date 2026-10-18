"""Generate static Git/Difftastic reports without shell data processing."""
import base64
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from functools import partial
from dataclasses import dataclass
from report_runtime import find_tool, output_parser, render, timestamp, tool_command, write_json, report_snapshot, ensure_site

TEMPLATES = Path(__file__).resolve().parent.parent / 'templates'


def git_query(project, *args):
    if args[0] == 'diff':
        args = ('diff', '--ignore-submodules=all', *args[1:])
    return subprocess.check_output(['git', *args], env=dict(os.environ, GIT_EXTERNAL_DIFF=''), stderr=subprocess.PIPE, cwd=project)


def b64(value):
    return base64.b64encode(value).decode('ascii')


def comparison_scope(git, revisions):
    # Git's ignore-submodules flag still emits regular-file/gitlink type changes.
    records = iter(git('diff', '--raw', '-z', '--diff-filter=T', *revisions, '--').split(b'\0'))
    excluded = []
    for header in records:
        if not header:
            continue
        name = next(records)
        old_mode, new_mode = header.split()[:2]
        if b'160000' in (old_mode[1:], new_mode):
            excluded.append(':(exclude,literal)' + os.fsdecode(name))
    return [*revisions, '--', *excluded]


def structural_payload(git, project, comparison, executable, env, *, include_worktree):
    # Raw -z records preserve tabs/newlines and avoid quoting or executing filenames.
    records = iter(git('diff', '--raw', '-z', '--no-abbrev', *comparison).split(b'\0'))
    lines = []
    with tempfile.TemporaryDirectory() as directory:
        for header in records:
            if not header:
                continue
            old_mode, new_mode, old_oid, new_oid, status = header.split()
            name = next(records)
            if status.startswith((b'R', b'C')):
                name = next(records)
            sources = []
            for side, oid in enumerate((old_oid, new_oid)):
                if set(oid) == {48}:
                    content = b''
                    # Zero OIDs also represent deleted sides, which must never read
                    # an unrelated, re-created file from the current working tree.
                    if side == 1 and include_worktree and new_mode != b'000000':
                        path = project / os.fsdecode(name)
                        if path.is_symlink():
                            content = os.fsencode(os.readlink(path))
                        elif path.is_file():
                            content = path.read_bytes()
                else:
                    content = git('cat-file', 'blob', oid.decode())
                sources.append(content)
            paths = [Path(directory) / 'old', Path(directory) / 'new']
            for path, source in zip(paths, sources):
                path.write_bytes(source)
            # Match Git's external-diff argument contract, including the display path.
            result = subprocess.run(tool_command(executable, os.fsdecode(name), str(paths[0]), old_oid.decode(), old_mode[1:].decode(),
                                     str(paths[1]), new_oid.decode(), new_mode.decode()), env=env,
                                    capture_output=True, check=True)
            if result.stdout.strip():
                json.loads(result.stdout)
                lines.append('\t'.join([b64(sources[0]), b64(sources[1]), b64(result.stdout)]))
    return ('\n'.join(lines) + ('\n' if lines else '')).encode()


@dataclass(frozen=True)
class ComparisonPlan:
    base: str
    compare: str | None

    @property
    def include_worktree(self):
        return self.compare is None

    @property
    def revisions(self):
        return [self.base] if self.include_worktree else [self.base + '...' + self.compare]

    @classmethod
    def resolve(cls, git, args):
        mode = os.environ.get('GIT_INCLUDE_UNCOMMITTED', 'true')
        if mode not in ('true', 'false'):
            raise ValueError('GIT_INCLUDE_UNCOMMITTED must be true or false')
        base = git('rev-parse', '--verify', '--end-of-options', args.base_ref + '^{commit}').decode().strip()
        compare = None if mode == 'true' else git('rev-parse', '--verify', '--end-of-options', args.compare_ref + '^{commit}').decode().strip()
        return cls(base, compare)


def generate():
    parser = output_parser('diff-reports', 'Generate an HTML Git and Difftastic report.', git_project=True)
    parser.add_argument('--base-ref', default=os.environ.get('GIT_BASE_REF', 'main'))
    parser.add_argument('--compare-ref', default=os.environ.get('GIT_COMPARE_REF', 'HEAD'))
    args = parser.parse_args()
    with report_snapshot(args.output_dir) as (staged, published):
        generate_into(args, staged)
        assemble_site(staged)
    print(f'Diff report generated: {published / "diff/index.html"}')


def generate_into(args, output):
    git = partial(git_query, args.project_dir)
    width = os.environ.get('DIFFTASTIC_WIDTH', '160')
    limit = os.environ.get('DIFFTASTIC_PARSE_ERROR_LIMIT', '100')
    skip = os.environ.get('DIFFTASTIC_SKIP_UNCHANGED', 'true')
    if not re.fullmatch('[1-9][0-9]*', width) or not re.fullmatch('[0-9]+', limit) or skip not in ('true', 'false'):
        raise ValueError('Invalid Difftastic width, parse error limit or skip-unchanged setting.')
    plan = ComparisonPlan.resolve(git, args)
    comparison = comparison_scope(git, plan.revisions)
    directory = output / 'diff'
    directory.mkdir(parents=True, exist_ok=True)
    numstat = iter(git('diff', '--no-ext-diff', '--numstat', '-z', *comparison).split(b'\0'))
    entries = []
    for entry in numstat:
        if entry:
            added, removed, name = entry.split(b'\t', 2)
            if not name:
                next(numstat)  # Rename source and destination occupy separate NUL fields.
                next(numstat)
            entries.append((added, removed, name))
    executable = find_tool(os.environ.get('DIFFTASTIC_COMMAND', 'difft'))
    stats = dict(generation_time=timestamp(), base_ref=args.base_ref, compare_ref=args.compare_ref if not plan.include_worktree else "working tree",
                 base_commit=plan.base, compare_commit=plan.compare,
                 files_changed=len(entries), insertions=sum(int(a) for a, _, _ in entries if a.isdigit()),
                 deletions=sum(int(b) for _, b, _ in entries if b.isdigit()), difftastic_available=bool(executable),
                 difftastic_skip_unchanged=skip == 'true', difftastic_parse_error_limit=int(limit))
    patch = git('diff', '--no-ext-diff', '--no-color', *comparison).decode('utf-8', errors='replace')
    fragments = []
    for line in patch.splitlines():
        kind = 'info' if line.startswith('@@') else 'add' if line.startswith('+') else 'remove' if line.startswith('-') else 'context'
        fragments.append(f'<div class="diff-line diff-{kind}">{html.escape(line)}</div>')
    git_html = '\n'.join(fragments) or '<div class="no-diff">No Git diff available</div>'
    structural = '<div class="no-diff">Difftastic executable was not found</div>'
    structural_ready = False
    if executable:
        env = dict(os.environ, DFT_UNSTABLE='yes', DFT_DISPLAY='json', DFT_WIDTH=width,
                   DFT_SKIP_UNCHANGED=skip, DFT_PARSE_ERROR_LIMIT=limit)
        try:
            payload = structural_payload(git, args.project_dir, comparison, executable, env, include_worktree=plan.include_worktree)
            structural_ready = True
            (directory / 'difftastic.jsonl').write_bytes(payload)
            structural = render(TEMPLATES / 'difftastic-content.html', {'PAYLOAD': b64(payload)}) if payload else '<div class="no-diff">No Difftastic diff available</div>'
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            print(f'Warning: Difftastic generation failed: {type(error).__name__}')
            structural = '<div class="no-diff">Difftastic failed to generate JSON output</div>'
    (directory / 'git-diff-content.html').write_text(git_html, encoding='utf-8')
    (directory / 'difftastic-diff-content.html').write_text(structural, encoding='utf-8')
    stats['difftastic_status'] = 'ready' if structural_ready else ('failed' if executable else 'unavailable')
    write_json(directory / 'stats.json', stats)
    values = {key.upper(): value for key, value in stats.items()}
    values.update(DIFFTASTIC_DISABLED='' if structural_ready else ' disabled', GIT_SELECTED='' if structural_ready else ' selected',
                  DIFFTASTIC_SELECTED=' selected' if structural_ready else '', GIT_VIEW_HIDDEN=' hidden' if structural_ready else '',
                  DIFFTASTIC_VIEW_HIDDEN='' if structural_ready else ' hidden', DIFFTASTIC_NOTE='Choose the renderer used for this comparison.' if structural_ready else ('Difftastic failed; showing Git diff.' if executable else 'Difftastic is unavailable.'))
    page = render(TEMPLATES / 'diff-report.html', values)
    page = page.replace('<div class="no-diff">Loading Git diff...</div>', git_html).replace('<div class="no-diff">Loading Difftastic diff...</div>', structural)
    (directory / 'index.html').write_text(page, encoding='utf-8')
    shutil.copyfile(TEMPLATES / 'diff-report.css', directory / 'diff-report.css')


def site():
    args = output_parser('diff-reports', 'Assemble a static diff site.', git_project=True).parse_args()
    published = ensure_site(args.output_dir, assemble_site)
    print(f'Diff site generated: {published / "index.html"}')


def assemble_site(output):
    output.mkdir(parents=True, exist_ok=True)
    section = 'No diff report generated. Run generate-diff-report.sh first.'
    if (output / 'diff/index.html').is_file():
        section = '<a href="diff/index.html" class="btn">View Full Diff</a>'
        stats_file = output / 'diff/stats.json'
        if stats_file.exists():
            stats = json.loads(stats_file.read_text(encoding='utf-8'))
            section = f'<p>{int(stats["files_changed"])} file(s) changed. Git line stats: +{int(stats["insertions"])} / -{int(stats["deletions"])}</p>' + section
    page = render(TEMPLATES / 'diff-site.html', {'GENERATED_AT': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'DIFF_SECTION': section})
    (output / 'index.html').write_text(page, encoding='utf-8')
    shutil.copyfile(TEMPLATES / 'style.css', output / 'style.css')
