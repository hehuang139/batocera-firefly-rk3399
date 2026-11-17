#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compare all SquashFS inode metadata and independently read adapted payloads."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess

SOURCE = Path(__file__).resolve().parent


def listing(image):
    data = subprocess.check_output(['unsquashfs', '-lln', str(image)], text=True)
    return parse_listing(data)


def parse_listing(data):
    result = {}
    pattern = re.compile(r'^(\S+) (\d+)/(\d+)\s+(\d+(?:,\s*\d+)?) (\S+) (\S+) squashfs-root(?:/(.*))?$')
    for line in data.splitlines():
        match = pattern.match(line)
        if not match:
            raise ValueError('Unparsed SquashFS metadata: ' + line)
        mode, uid, gid, size, date, time, name = match.groups()
        name = name or ''
        link = None
        if mode.startswith('l'):
            name, link = name.split(' -> ', 1)
        if name in result:
            raise ValueError('Duplicate SquashFS path: ' + name)
        result[name] = dict(mode=mode, uid=uid, gid=gid, size=size, date=date, time=time, link=link)
    return result


def read(image, path):
    return subprocess.check_output(['unsquashfs', '-cat', str(image), path])


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('before', type=Path)
    p.add_argument('after', type=Path)
    p.add_argument('adaptation_report', type=Path)
    p.add_argument('report', type=Path)
    a = p.parse_args()
    edits = {item['path']: item for item in json.loads(a.adaptation_report.read_text())['files']}
    old, new = listing(a.before), listing(a.after)
    expected_additions = {name for name, item in edits.items() if item['before_sha256'] is None}
    assert set(new) - set(old) == expected_additions
    assert not set(old) - set(new)
    for name in expected_additions:
        assert new[name]['uid'] == '0' and new[name]['gid'] == '0', (name, 'new file ownership', new[name])
        expected_mode = stat.filemode(stat.S_IFREG | int(edits[name]['mode'], 8))
        assert new[name]['mode'] == expected_mode, (name, 'new file mode', new[name], expected_mode)
    for name in set(old) & set(new):
        first, second = old[name], new[name]
        for key in ['mode', 'uid', 'gid', 'link']:
            assert first[key] == second[key], (name, key, first, second)
        if not first['mode'].startswith('d') and name not in edits:
            assert first == second, (name, first, second)
    checks = []
    for name, item in edits.items():
        assert sha(read(a.after, name)) == item['after_sha256'], name
        if item['before_sha256'] is not None:
            assert sha(read(a.before, name)) == item['before_sha256'], name
        checks.append(name)
    preserved = [
        'usr/bin/emulationstation', 'usr/bin/retroarch',
        'usr/lib/libEGL.so.1', 'usr/share/batocera/batocera.arch',
        'usr/share/batocera/batocera.version',
        'lib/firmware/brcm/BCM4356A2.hcd',
        'lib/firmware/brcm/brcmfmac4356-sdio.bin',
        'lib/firmware/brcm/brcmfmac4356-sdio.txt',
        'lib/firmware/brcm/brcmfmac4356-sdio.clm_blob',
    ]
    # Follow symlinks using the known SquashFS target, not the host filesystem.
    def resolve(name):
        import posixpath
        seen = set()
        while new[name]['link']:
            assert name not in seen
            seen.add(name)
            target = new[name]['link']
            name = posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join(posixpath.dirname(name), target))
        return name
    hashes = {}
    for name in preserved:
        target = resolve(name)
        before_hash, after_hash = sha(read(a.before, target)), sha(read(a.after, target))
        assert before_hash == after_hash, name
        hashes[name] = after_hash
    assert read(a.after, 'usr/share/batocera/batocera.arch').strip() == b'rk3399'
    a.report.write_text(json.dumps({'result':'PASS', 'old_paths':len(old), 'new_paths':len(new),
        'metadata_checked':len(set(old)&set(new)), 'adapted_files_checked':checks,
        'preserved_payloads':hashes}, indent=2)+'\n')
    print('Rootfs metadata and payload comparison: PASS', len(new), 'paths')


if __name__ == '__main__':
    main()
