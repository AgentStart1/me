"""Prepare a new OpenCore image; never modify the supplied firmware or system disk."""
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import plistlib
import shutil
import urllib.request
import zipfile

from reims_sources import ROOT, Input

DRIVER = ROOT / 'drivers/pvg-timing-fix'


@dataclass(frozen=True)
class DriverSnapshot:
    build: str
    architecture: str
    files: tuple[Input, ...]

    def file(self, name):
        return next(item.content for item in self.files if item.name == name)


def verified_driver(build):
    manifest = json.loads((DRIVER / 'artifact.json').read_text())
    if build != manifest['build']:
        raise ValueError('Timing driver is qualified only for macOS build ' + manifest['build'])
    files = []
    for name, expected in manifest['files'].items():
        if Path(name).name != name:
            raise ValueError('Timing driver artifact verification failed')
        content = (DRIVER / name).read_bytes()
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError('Timing driver artifact verification failed')
        files.append(Input(name, content))
    if not {'Info.plist', 'PvgTimingFix'} <= {item.name for item in files}:
        raise ValueError('Timing driver artifact is incomplete')
    return DriverSnapshot(build, manifest['architecture'], tuple(files))


def lilu_files(archive, expected):
    content = archive.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected:
        raise ValueError('Lilu archive checksum mismatch')
    files = {}
    with zipfile.ZipFile(io.BytesIO(content)) as source:
        for item in source.infolist():
            if item.is_dir() or not item.filename.startswith('Lilu.kext/'):
                continue
            path = PurePosixPath(item.filename)
            if '..' in path.parts or path.is_absolute() or (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Invalid Lilu bundle archive entry')
            files[str(path)] = source.read(item)
    if 'Lilu.kext/Contents/MacOS/Lilu' not in files or 'Lilu.kext/Contents/Info.plist' not in files:
        raise ValueError('Lilu bundle is incomplete')
    return files


def prepare(source, output, build, lilu_archive=None, offset=1048576):
    driver = verified_driver(build)
    source, output = Path(source).resolve(), Path(output).resolve()
    receipt_path = output.with_suffix(output.suffix + '.json')
    if (output == source or receipt_path.resolve() == source or output.exists()
            or receipt_path.exists() or receipt_path.is_symlink()):
        raise ValueError('Select a new image and receipt; existing files are never overwritten')
    if type(offset) is not int or offset < 0 or offset % 512:
        raise ValueError('FAT partition offset must be a nonnegative sector boundary')
    lock = json.loads((ROOT / 'patches/reims-windows/sources.json').read_text())['guest']
    archive = Path(lilu_archive) if lilu_archive else output.parent / 'Lilu-1.7.2-RELEASE.zip'
    if not archive.exists():
        with urllib.request.urlopen(lock['lilu_url'], timeout=60) as response, archive.open('xb') as stream:
            shutil.copyfileobj(response, stream)
    files = lilu_files(archive, lock['lilu_sha256'])
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    # Reserve both destinations exclusively. A failed attempt retains its new
    # partial outputs for inspection, never replaces an existing receipt/image.
    with receipt_path.open('x', encoding='utf-8', newline='\n') as report:
        return write_image(source, output, driver, files, before, lock, offset, report)


def write_image(source, output, driver, files, before, lock, offset, report):
    from pyfatfs.PyFatFS import PyFatFS
    with source.open('rb') as original, output.open('xb') as copied:
        shutil.copyfileobj(original, copied)
    with PyFatFS(str(output), offset=offset) as fat:
        config = plistlib.loads(fat.readbytes('/EFI/OC/config.plist'))
        entries = config['Kernel']['Add']
        if len([item for item in entries if item['BundlePath'] == 'Lilu.kext' and item['Enabled']]) != 1:
            raise ValueError('OpenCore must contain exactly one enabled Lilu entry')
        for name in ('Lilu.kext', 'PvgTimingFix.kext'):
            path = '/EFI/OC/Kexts/' + name
            if fat.exists(path):
                fat.removetree(path)
        for name, content in files.items():
            path = '/EFI/OC/Kexts/' + name
            fat.makedirs(str(PurePosixPath(path).parent), recreate=True)
            fat.writebytes(path, content)
        directory = '/EFI/OC/Kexts/PvgTimingFix.kext/Contents'
        fat.makedirs(directory + '/MacOS', recreate=True)
        payload = {directory + '/Info.plist': driver.file('Info.plist'),
                   directory + '/MacOS/PvgTimingFix': driver.file('PvgTimingFix')}
        for path, content in payload.items():
            if fat.exists(path):
                fat.remove(path)
            fat.writebytes(path, content)
            if fat.readbytes(path) != content:
                raise ValueError('Boot driver artifact readback failed')
        if fat.readbytes('/EFI/OC/Kexts/Lilu.kext/Contents/MacOS/Lilu') != files['Lilu.kext/Contents/MacOS/Lilu']:
            raise ValueError('Lilu artifact readback failed')
        entries[:] = [item for item in entries if item['BundlePath'] != 'PvgTimingFix.kext']
        entries.append({'Arch': 'x86_64', 'BundlePath': 'PvgTimingFix.kext',
                        'Comment': 'Audited macOS 15.8.1 fixed display timing', 'Enabled': True,
                        'ExecutablePath': 'Contents/MacOS/PvgTimingFix', 'MinKernel': '24.0.0',
                        'MaxKernel': '24.99.99', 'PlistPath': 'Contents/Info.plist'})
        config['Misc']['Boot']['ShowPicker'] = False
        config['Misc']['Boot']['PollAppleHotKeys'] = False
        # Inherited logging configurations may otherwise halt on boot fallback logs.
        config['Misc']['Security']['HaltLevel'] = 0
        fat.remove('/EFI/OC/config.plist')
        fat.writebytes('/EFI/OC/config.plist', plistlib.dumps(config))
        if plistlib.loads(fat.readbytes('/EFI/OC/config.plist')) != config:
            raise ValueError('OpenCore configuration readback failed')
    if hashlib.sha256(source.read_bytes()).hexdigest() != before:
        raise ValueError('Source firmware changed during preparation')
    receipt = {'source_sha256': before, 'output_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
               'guest_build': driver.build, 'driver_sha256': hashlib.sha256(driver.file('PvgTimingFix')).hexdigest(),
               'lilu_sha256': lock['lilu_sha256'], 'source_modified': False}
    report.write(json.dumps(receipt, indent=2) + '\n')
    return receipt
