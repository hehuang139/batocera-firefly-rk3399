#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Restore the two large fixed inputs omitted from Git, using the full source archive."""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8388608), b''): h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive', type=Path)
    a = p.parse_args()
    if a.archive.is_symlink() or not stat.S_ISREG(a.archive.stat().st_mode):
        p.error('Source archive must be an ordinary file')
    inputs = json.loads((HERE / 'inputs.json').read_text())
    with tarfile.open(a.archive, 'r:gz') as archive:
        for key in ['secondary', 'share']:
            item = inputs['components'][key]
            path = ROOT / item['path']
            if path.is_symlink(): raise ValueError('Refusing symlink destination')
            if path.exists():
                if not path.is_file() or path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
                    raise ValueError('Existing asset differs: ' + str(path))
                print('Already correct: ' + str(path))
                continue
            member = archive.getmember('firefly-rk3399-batocera/' + item['path'])
            if not member.isfile() or member.size != item['bytes']:
                raise ValueError('Wrong source member: ' + member.name)
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='.asset-', dir=path.parent) as temporary:
                scratch = Path(temporary) / 'asset'
                h = hashlib.sha256()
                with archive.extractfile(member) as source, scratch.open('xb') as target:
                    for block in iter(lambda: source.read(8388608), b''):
                        target.write(block); h.update(block)
                if scratch.stat().st_size != item['bytes'] or h.hexdigest() != item['sha256']:
                    raise ValueError('Source asset checksum mismatch')
                scratch.chmod(0o644)
                # Hard link refuses an output created concurrently instead of overwriting it.
                path.hardlink_to(scratch)
            print('Restored and verified: ' + str(path))


if __name__ == '__main__': main()
