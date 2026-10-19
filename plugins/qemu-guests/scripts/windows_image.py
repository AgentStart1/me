"""Resolve actual WIM image names and Core/Desktop variants before disk creation."""
import re
import struct
import xml.etree.ElementTree as ET


def editions(path):
    import pycdlib
    iso = pycdlib.PyCdlib()
    iso.open(str(path))
    try:
        key = 'udf_path' if iso.has_udf() else 'joliet_path'
        for filename in ('install.wim', 'install.esd'):
            try:
                source = iso.open_file_from_iso(**{key: '/sources/' + filename})
                break
            except pycdlib.pycdlibexception.PyCdlibException:
                continue
        else:
            raise ValueError('Windows media has no sources/install.wim or install.esd')
        with source as wim:
            header = wim.read(208)
            if len(header) < 96 or header[:8] != b'MSWIM\0\0\0':
                raise ValueError('Invalid Windows WIM header')
            length = struct.unpack_from('<Q', header, 72)[0] & 0x00ffffffffffffff
            offset = struct.unpack_from('<Q', header, 80)[0]
            if not 0 < length <= 16 * 1024 * 1024:
                raise ValueError('Invalid Windows edition metadata length')
            wim.seek(offset)
            xml = ET.fromstring(wim.read(length).decode('utf-16'))
        return [{'name': node.findtext('NAME'), 'type': node.findtext('WINDOWS/INSTALLATIONTYPE', '')}
                for node in xml.findall('IMAGE')]
    finally:
        iso.close()


def select(items, requested, graphical):
    def family(name):
        value = re.sub(r'\s*\(desktop experience\)$', '', name, flags=re.I)
        return re.sub(r'CORE$', '', value, flags=re.I).casefold()
    candidates = [item for item in items if family(item['name']) == family(requested)]
    for item in candidates:
        is_core = 'core' in item['type'].casefold()
        if is_core == (not graphical):
            return item['name']
    raise ValueError('Windows media has no matching graphical/Core edition; inspect its WIM image names')
