#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build a regular TF image file; never writes a disk device."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys

SOURCE = Path(__file__).resolve().parent
BOOT_START = 16777216
IMAGE_SIZE = 4580179968


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def regular(path):
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f'Expected a regular file: {path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_gz', type=Path)
    parser.add_argument('rootfs_squashfs', type=Path)
    parser.add_argument('output_img', type=Path)
    args = parser.parse_args()
    assets = SOURCE / 'boot-assets'
    sidecar = args.output_img.with_suffix('.manifest.json')
    if sidecar.exists() or sidecar.is_symlink():
        raise ValueError('Refusing to overwrite an existing manifest')
    manifest = json.loads((SOURCE / 'base-manifest.json').read_text())
    for path in [args.base_gz, args.rootfs_squashfs]:
        regular(path)
    if digest(args.base_gz) != manifest['sha256']:
        raise ValueError('Official base image checksum mismatch')
    with args.rootfs_squashfs.open('rb') as f:
        if f.read(4) != b'hsqs':
            raise ValueError('Not a SquashFS root filesystem')
    if args.output_img.exists() or args.output_img.is_symlink() or args.output_img.suffix != '.img':
        raise ValueError('Output must be a new .img file')
    required = ['idbloader.img', 'u-boot.itb', 'rk3399-firefly-batocera-sd.dtb',
                'extlinux.conf', 'batocera.board']
    for name in required:
        regular(assets / name)
    with gzip.open(args.base_gz, 'rb') as src, args.output_img.open('xb') as dst:
        shutil.copyfileobj(src, dst, 8 * 1024 * 1024)
    if args.output_img.stat().st_size != IMAGE_SIZE:
        raise ValueError('Unexpected raw image length')
    with args.output_img.open('r+b') as f:
        mbr = f.read(512)
        if mbr[510:] != b'\x55\xaa':
            raise ValueError('MBR signature is invalid')
        for index, expected in enumerate([(12, 32768, 8388608), (131, 8421376, 524288)]):
            row = struct.unpack('<B3sB3sII', mbr[446 + index * 16:462 + index * 16])
            if (row[2], row[4], row[5]) != expected:
                raise ValueError('Unexpected partition geometry')
        # Clear donor loaders and saved environments, preserving the MBR.
        f.seek(512)
        f.write(bytes(BOOT_START - 512))
        for name, offset, limit in [('idbloader.img', 32768, 8388608),
                                     ('u-boot.itb', 8388608, BOOT_START)]:
            data = (assets / name).read_bytes()
            if offset + len(data) > limit:
                raise ValueError('Boot component overlaps partition/next component')
            f.seek(offset)
            f.write(data)
    drive = f'{args.output_img}@@{BOOT_START}'
    for path, target in [(args.rootfs_squashfs, '::/boot/batocera'),
                         (assets / required[2], '::/boot/' + required[2]),
                         (assets / 'extlinux.conf', '::/extlinux/extlinux.conf'),
                         (assets / 'batocera.board', '::/boot/batocera.board'),
                         (SOURCE / 'collect-logs.sh', '::/collect-logs.sh'),
                         (SOURCE / 'docs/刷卡与首启.md', '::/FIREFLY-README.txt')]:
        subprocess.run(['mcopy', '-o', '-i', drive, str(path), target], check=True)
    subprocess.run(['mdel', '-i', drive, '::/boot/rk3399-rockpro64.dtb'], check=True)
    # Erase released FAT clusters so the image does not carry a second, stale
    # copy of the donor SquashFS in unallocated space.
    subprocess.run([sys.executable, str(SOURCE / 'zero-free-fat.py'),
                    str(args.output_img)], check=True)
    with args.output_img.open('rb') as f:
        if f.read(512) != mbr:
            raise ValueError('MBR was modified')
    report = {'image': args.output_img.name, 'bytes': IMAGE_SIZE,
              'sha256': digest(args.output_img),
              'base_sha256': manifest['sha256'],
              'rootfs_sha256': digest(args.rootfs_squashfs),
              'free_fat_clusters_zeroed': True,
              'boot_assets': {n: digest(assets / n) for n in required}}
    with sidecar.open('x') as f:
        f.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
