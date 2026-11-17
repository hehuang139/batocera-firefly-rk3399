#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Record every filesystem path, inode metadata, link and regular-file digest."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8388608), b''):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    root = a.root.resolve(strict=True)
    if root == Path('/'):
        raise ValueError('Expected an extracted image tree')
    files = {}
    paths = [root]
    for directory, directories, names in os.walk(root, followlinks=False):
        paths.extend(Path(directory) / name for name in directories + names)
    for path in sorted(paths):
        metadata = path.lstat()
        item = {'mode': stat.S_IMODE(metadata.st_mode), 'type': stat.S_IFMT(metadata.st_mode),
                'uid': metadata.st_uid, 'gid': metadata.st_gid, 'mtime': metadata.st_mtime_ns}
        if stat.S_ISREG(metadata.st_mode):
            item.update(bytes=metadata.st_size, sha256=digest(path))
        elif stat.S_ISLNK(metadata.st_mode):
            item['target'] = os.readlink(path)
        elif not stat.S_ISDIR(metadata.st_mode):
            item['device'] = metadata.st_rdev
        files[path.relative_to(root).as_posix()] = item
    report = {'root': str(root), 'paths': len(files), 'regular_files': sum('sha256' in x for x in files.values()),
              'files': files}
    with a.output.open('x') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'files'}))


if __name__ == '__main__':
    main()
