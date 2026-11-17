#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Rebuild 43.1 from two pinned official releases; all writes are ordinary files."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def run(*args):
    subprocess.run([str(x) for x in args], check=True)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8388608), b''): h.update(block)
    return h.hexdigest()


def pin(path, item):
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('Expected ordinary file: ' + str(path))
    if path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
        raise ValueError('Pinned input mismatch: ' + str(path))


def new_directory(path):
    if path.exists() or path.is_symlink():
        raise ValueError('Use a new directory: ' + str(path))
    path.mkdir(parents=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('bsp40', type=Path, help='Pinned official RockPro64 v40 .img.gz')
    p.add_argument('userspace431', type=Path, help='Pinned official N2+ v43.1 boot.tar.xz')
    p.add_argument('output', type=Path, help='New directory within this project')
    p.add_argument('--scratch', type=Path, required=True, help='New directory; allow at least 25 GiB')
    p.add_argument('--rootfs-only', action='store_true', help='Rebuild and verify the fixed system, then stop before disk assembly')
    a = p.parse_args()
    if os.geteuid() != 0:
        p.error('Run inside the supplied Docker builder as root to preserve image ownership')
    # Validate every fixed component and both upstream inputs before creating output.
    pin(a.bsp40, json.loads((ROOT / 'source/base-manifest.json').read_text()))
    pin(a.userspace431, json.loads((HERE / 'provenance/base-manifest.json').read_text()))
    inputs = json.loads((HERE / 'inputs.json').read_text())
    for group in [inputs['components'], inputs['documents'], *inputs['boot_assets'].values()]:
        for item in group.values(): pin(ROOT / item['path'], item)
    out = a.output.absolute()
    if not out.resolve().is_relative_to(ROOT) or out.resolve() == ROOT:
        p.error('Output must be a new directory within this project')
    if out.exists() or out.is_symlink() or a.scratch.exists() or a.scratch.is_symlink():
        p.error('Output and scratch must both be new directories')
    if out.resolve().is_relative_to(a.scratch.resolve()) or a.scratch.resolve().is_relative_to(out.resolve()):
        p.error('Output and scratch must be separate directories')
    new_directory(out)
    new_directory(a.scratch)
    validation = out / 'validation'
    validation.mkdir()
    stage = a.scratch.resolve()
    raw = stage / 'bsp40.img'
    with gzip.open(a.bsp40, 'rb') as source, raw.open('xb') as target:
        shutil.copyfileobj(source, target, 8388608)
    bsp_sqfs = stage / 'bsp40.squashfs'
    run('mcopy', '-i', str(raw) + '@@16777216', '::/boot/batocera', bsp_sqfs)
    bsp = stage / 'bsp-rootfs'
    run('unsquashfs', '-processors', '6', '-no-progress', '-d', bsp, bsp_sqfs,
        'lib/modules', 'lib/firmware', 'usr/share/batocera/batocera.arch')
    primary = stage / 'batocera.update'
    with tarfile.open(a.userspace431, 'r:xz') as archive:
        for name, target in [('boot/batocera.update', primary),
                             ('boot/rufomaculata.update', stage / 'rufomaculata'),
                             ('boot/initrd.lz4', stage / 'initrd.lz4')]:
            member = archive.getmember(name)
            if not member.isfile(): raise ValueError('Upstream member must be regular: ' + name)
            with archive.extractfile(member) as source, target.open('xb') as stream:
                shutil.copyfileobj(source, stream, 8388608)
    pin(stage / 'rufomaculata', inputs['components']['secondary'])
    pin(stage / 'initrd.lz4', inputs['components']['initrd'])
    root = stage / 'rootfs'
    run('unsquashfs', '-processors', '6', '-no-progress', '-d', root, primary)
    run(sys.executable, HERE / 'inventory.py', root, stage / 'before.json')
    run(sys.executable, HERE / 'rootfs/apply.py', '--rootfs', root, '--bsp-rootfs', bsp,
        '--report', validation / 'adaptation.json')
    run(sys.executable, HERE / 'rootfs/validate.py', '--rootfs', root, '--bsp-rootfs', bsp,
        '--report', validation / 'behavior.json')
    # Retain release timestamps too, so rebuilding can reproduce the fixed system hash.
    final = json.loads((HERE / 'provenance/final-content.json').read_text())['files']
    for name, item in final.items():
        path = root if name == '.' else root / name
        os.utime(path, ns=(item['mtime'], item['mtime']), follow_symlinks=False)
    run(sys.executable, HERE / 'inventory.py', root, stage / 'after.json')
    run(sys.executable, HERE / 'compare-inventories.py', stage / 'before.json', stage / 'after.json',
        HERE / 'rootfs/provenance.json', validation / 'content-delta.json')
    system = stage / 'firefly431.squashfs'
    run('mksquashfs', root, system, '-noappend', '-no-duplicates', '-no-sparse', '-comp', 'zstd',
        '-Xcompression-level', '15', '-b', '131072', '-processors', '6', '-no-progress',
        '-mkfs-time', '1794873600')
    pin(system, inputs['rootfs'])
    (stage / 'packed-check').mkdir()
    run(sys.executable, HERE / 'verify-packed-rootfs.py', system, HERE / 'provenance/final-content.json',
        stage / 'packed-check', validation / 'packed-rootfs.json')
    if a.rootfs_only:
        print('Rebuilt exact release SquashFS and verified all contents: ' + str(system))
        return
    names = {'emmc': 'batocera431-firefly-rk3399-emmc-test1.img',
             'installer': 'batocera431-firefly-rk3399-emmc-installer-tf-test1.img'}
    for mode, name in names.items():
        image = out / name
        command = [sys.executable, HERE / 'make-image.py', mode, system, image]
        if mode == 'installer':
            command += ['--payload', out / (names['emmc'] + '.gz'), '--payload-manifest', out / 'manifest.json']
        run(*command)
        run('gzip', '-1', '-n', '-k', image)
        if mode == 'emmc':
            run(sys.executable, HERE / 'release-manifest.py', image, out / 'manifest.json')
    sums = [p for p in sorted(out.iterdir()) if p.is_file()]
    (out / 'SHA256SUMS').write_text(''.join(digest(path) + '  ' + path.name + '\n' for path in sums))
    for mode, name in names.items():
        run(sys.executable, HERE / 'verify-image.py', '--mode', mode, '--image', out / name,
            '--report', validation / (mode + '-image.json'), '--scratch', stage / (mode + '-verification'))
    print('Rebuilt and independently verified: ' + str(out))


if __name__ == '__main__': main()
