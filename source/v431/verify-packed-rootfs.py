#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read every packed regular file and compare all inode metadata with the tree."""
import argparse
import json
from pathlib import Path
import stat
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('squashfs', type=Path)
    p.add_argument('inventory', type=Path)
    p.add_argument('scratch', type=Path)
    p.add_argument('report', type=Path)
    a = p.parse_args()
    root = a.scratch / 'packed-rootfs'
    manifest = a.scratch / 'packed-inventory.json'
    if root.exists() or root.is_symlink() or manifest.exists() or manifest.is_symlink():
        raise ValueError('Packed verification paths must be new')
    subprocess.run(['unsquashfs', '-processors', '6', '-no-progress', '-d', str(root), str(a.squashfs)], check=True)
    subprocess.run([sys.executable, str(HERE / 'inventory.py'), str(root), str(manifest)], check=True)
    expected = json.loads(a.inventory.read_text())['files']
    actual = json.loads(manifest.read_text())['files']
    assert set(expected) == set(actual)
    regular = 0
    for name in expected:
        left, right = dict(expected[name]), dict(actual[name])
        # SquashFS stores timestamp precision in whole seconds.
        left['mtime'] = left['mtime'] // 1_000_000_000
        right['mtime'] = right['mtime'] // 1_000_000_000
        # mksquashfs sets the filesystem root to its -mkfs-time value.
        if name == '.':
            left.pop('mtime', None)
            right.pop('mtime', None)
        assert left == right, (name, left, right)
        regular += stat.S_ISREG(left['type'])
    report = {'result': 'PASS', 'paths_checked': len(actual), 'regular_file_contents_checked': regular,
              'metadata': ['type', 'mode', 'uid', 'gid', 'mtime', 'symlink target', 'regular size and SHA256']}
    a.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
