"""Collect bounded HTML/JUnit trees and assemble a static report index."""
import html
import os
from pathlib import Path
import re
import shutil
import hashlib
import subprocess
from urllib.parse import quote
from datetime import datetime
from report_runtime import output_parser, render, timestamp, write_json, report_snapshot, ensure_site, materialize_tree

TEMPLATES = Path(__file__).resolve().parent.parent / 'templates'
DEFAULT_DIRS = ('build/reports', 'app/build/reports', 'androidApp/build/reports',
                'shared/build/reports', 'build/test-results', 'app/build/test-results',
                'shared/build/test-results', 'target/surefire-reports',
                'target/failsafe-reports', 'test-results', 'test-reports', 'reports')


def submodule_directories(project):
    """Return registered gitlinks without requiring Git for non-Git projects."""
    executable = shutil.which('git')
    has_metadata = any((path / '.git').exists() or (path / '.gitmodules').exists()
                       for path in (project, *project.parents))
    if not executable:
        if has_metadata:
            raise ValueError('Git is required to exclude submodules when collecting from a Git repository.')
        return set()
    result = subprocess.run([executable, '-C', str(project), 'rev-parse', '--show-toplevel'], capture_output=True)
    if result.returncode:
        if has_metadata:
            raise subprocess.CalledProcessError(result.returncode, result.args)
        return set()
    root = Path(os.fsdecode(result.stdout.rstrip(b'\r\n'))).resolve()
    entries = subprocess.check_output([executable, '-C', str(root), 'ls-files', '--stage', '-z'])
    paths = {os.fsdecode(entry.split(b'\t', 1)[1]) for entry in entries.split(b'\0')
             if entry.startswith(b'160000 ')}
    modules = root / '.gitmodules'
    if modules.is_file():
        config = subprocess.run([executable, 'config', '--file', str(modules), '--null',
                                 '--get-regexp', r'^submodule\..*\.path$'], capture_output=True)
        if config.returncode not in (0, 1):
            raise subprocess.CalledProcessError(config.returncode, config.args)
        paths.update(os.fsdecode(entry.partition(b'\n')[2]) for entry in config.stdout.split(b'\0') if entry)
    return {path for name in paths if (path := (root / name).resolve()).is_relative_to(root)}


def inside_submodule(path, submodules):
    path = path.resolve()
    return any(path == module or module in path.parents for module in submodules)


def bounded_files(root, output, submodules):
    """Find files at GNU find -maxdepth 4 depth, pruning output and directory links."""
    for directory, children, files in os.walk(root, followlinks=False):
        path = Path(directory)
        depth = len(path.relative_to(root).parts)
        children[:] = sorted(child for child in children
                             if depth < 3 and (path / child).resolve() != output
                             and child != '.git' and not inside_submodule(path / child, submodules)
                             and not (path / child).is_symlink())
        if path.resolve() == output:
            children.clear()
            continue
        for name in sorted(files):
            if not inside_submodule(path / name, submodules):
                yield path / name


def collect():
    parser = output_parser('test-reports', 'Collect HTML and JUnit test reports.')
    parser.add_argument('--test-dirs', help='Legacy colon-separated directories (use --test-dir for drive paths).')
    parser.add_argument('--test-dir', action='append', default=[], type=Path, help='Additional directory; repeat as needed.')
    args = parser.parse_args()
    with report_snapshot(args.output_dir) as (staged, published):
        counts = collect_into(args, staged)
        assemble_site(staged)
    print(f'Collection complete: {counts[0]} reports, {counts[1]} standalone XML files')
    print(f'Report site generated: {published / "index.html"}')


def collect_into(args, output):
    excluded_output = args.output_dir.resolve()
    def project_path(value):
        path = Path(value)
        return (path if path.is_absolute() else args.project_dir / path).resolve()
    custom = args.test_dirs if args.test_dirs is not None else os.environ.get('TEST_RESULT_DIRS', os.environ.get('REPORT_DIRS', ''))
    roots = {project_path(path) for path in [*DEFAULT_DIRS, *args.test_dir, *filter(None, (custom or '').split(':'))]
             if project_path(path).is_dir()}
    submodules = set().union(*(submodule_directories(root) for root in roots | {args.project_dir}))
    roots = {root for root in roots if not inside_submodule(root, submodules)}
    roots = sorted(roots, key=lambda path: (len(path.parts), str(path)))
    candidates = {}
    xml_files = set()
    for root in roots:
        for file in bounded_files(root, excluded_output, submodules):
            if file.name == 'index.html':
                candidates.setdefault(file.parent, root)
            if file.match('*-tests.xml') or file.match('TEST-*.xml'):
                xml_files.add(file.resolve())
    selected = []
    for candidate in sorted(candidates, key=lambda path: (len(path.parts), str(path))):
        if not any(candidate == parent or parent in candidate.parents for parent in selected):
            if candidate == excluded_output or candidate in excluded_output.parents:
                raise ValueError('Output directory must be outside a report being copied.')
            selected.append(candidate)
    (output / 'reports').mkdir(parents=True, exist_ok=True)
    (output / 'test-results').mkdir(parents=True, exist_ok=True)
    reports = []
    def ignore_submodules(directory, names):
        return [name for name in names if name == '.git' or inside_submodule(Path(directory) / name, submodules)
                or (Path(directory) / name).resolve() == excluded_output
                or excluded_output in (Path(directory) / name).resolve().parents]
    for candidate in selected:
        relative = candidate.relative_to(candidates[candidate]).as_posix()
        name = re.sub(r'[^\w.-]', '_', relative.replace('/', '-')).strip('-')
        if name in ('', '.'):
            name = 'report'
        destination = output / 'reports' / name
        suffix = 0
        while destination.exists():
            suffix += 1
            destination = output / 'reports' / f'{name}-{suffix}'
        materialize_tree(candidate, destination, ignore=ignore_submodules)
        index = destination / 'index.html'
        page = index.read_text(encoding='utf-8')
        for asset, attribute in (('css', 'href'), ('js', 'src')):
            source = candidate.parent / asset
            if f'../{asset}/' in page and source.is_dir():
                materialize_tree(source, destination / asset, dirs_exist_ok=True, ignore=ignore_submodules)
                page = page.replace(f'{attribute}="../{asset}/', f'{attribute}="{asset}/')
        index.write_text(page, encoding='utf-8')
        reports.append(destination.relative_to(output).as_posix())
    for source in sorted(xml_files):
        digest = hashlib.md5(str(source).encode()).hexdigest()
        name = re.sub(r'[^\w.$-]', '_', source.name)
        shutil.copyfile(source, output / 'test-results' / f'{digest}-{name}')
    write_json(output / 'reports/summary.json', dict(collection_time=timestamp(), total_reports=len(reports),
                                                   xml_files=len(xml_files), report_directories=reports))
    return len(reports), len(xml_files)


def site():
    args = output_parser('test-reports', 'Assemble a static test report site.').parse_args()
    published = ensure_site(args.output_dir, assemble_site)
    print(f'Report site generated: {published / "index.html"}')


def assemble_site(output):
    output.mkdir(parents=True, exist_ok=True)
    links = []
    for index in sorted((output / 'reports').glob('*/index.html')):
        name = index.parent.name
        display = name.replace('-', ' ').title()
        display = re.sub(r'\b(Api|Css|Html|Js|Xml)\b', lambda match: match[0].upper(), display)
        links.append(f'<a href="reports/{quote(name, safe="")}/index.html" class="btn">{html.escape(display)}</a>')
    if (output / 'reports/index.html').is_file():
        links.append('<a href="reports/index.html" class="btn">Main Report</a>')
    for file in sorted((output / 'test-results').glob('*.xml')):
        display = file.name.partition('-')[2]
        links.append(f'<a href="test-results/{quote(file.name, safe="")}" class="btn">{html.escape(display)} (JUnit XML)</a>')
    section = '\n'.join(links) if links else 'No reports found. Run your tests first to generate reports.'
    page = render(TEMPLATES / 'report-site.html', {'GENERATED_AT': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'REPORTS_SECTION': section})
    (output / 'index.html').write_text(page, encoding='utf-8')
    shutil.copyfile(TEMPLATES / 'style.css', output / 'style.css')
