#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify downloaded Release parts and join one complete .img.gz for Etcher."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat


def regular(path):
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('Expected ordinary file: ' + str(path))


def stream_hash(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(8388608), b''): h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest', type=Path, help='Downloaded .img.gz.parts.json')
    a = p.parse_args()
    regular(a.manifest)
    report = json.loads(a.manifest.read_text())
    image = report['image']
    name = image['name']
    if Path(name).name != name or not name.endswith('.img.gz'):
        raise ValueError('Invalid destination basename')
    output = a.manifest.parent / name
    if output.exists() or output.is_symlink(): raise ValueError('Output already exists: ' + str(output))
    parts = report['parts']
    if not parts or sum(item['bytes'] for item in parts) != image['bytes']:
        raise ValueError('Invalid part sizes')
    for index, item in enumerate(parts, 1):
        if item['name'] != name + '.part' + str(index).zfill(3): raise ValueError('Invalid part order')
        if not re.fullmatch('[0-9a-f]{64}', item['sha256']): raise ValueError('Invalid part hash')
        path = a.manifest.parent / item['name']
        regular(path)
        if path.stat().st_size != item['bytes'] or stream_hash(path) != item['sha256']:
            raise ValueError('Part checksum mismatch: ' + str(path))
    h, size = hashlib.sha256(), 0
    with output.open('xb') as target:
        for item in parts:
            with (a.manifest.parent / item['name']).open('rb') as source:
                for block in iter(lambda: source.read(8388608), b''):
                    target.write(block); h.update(block); size += len(block)
    if size != image['bytes'] or h.hexdigest() != image['sha256']:
        raise ValueError('Joined image checksum mismatch; delete the incomplete output before retrying')
    print('SHA256 verified: ' + h.hexdigest())
    print('Ready for Etcher: ' + str(output))


if __name__ == '__main__': main()
