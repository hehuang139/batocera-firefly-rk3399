#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Copy and repair the exact released Batocera 43.1 direct eMMC raw image."""
import argparse
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import tempfile

RAW_SIZE = 4580179968
RAW_TEST1 = 'd4c86a2ed8177b1b3a6dc9f25ca0a863516061ce963255f18af5edc4a2a97030'
RAW_VSEL1 = '92a916225d2b9239f0ca8e4570c316b55a914332f52c2cefa76dd36f370dc598'
DTB_TEST1 = '136f55b02480b046bb1d76f6757a46614bb81e5c975ee25ba273062e0a199598'
DTB_VSEL1 = 'f6e6455b3b717c4cd19fd45676e8a4a93a885b8f4da08ff100f6b6a08c452669'
FAT_OFFSET = 16777216
DTB_OFFSET = 427249664
BANK_OFFSET = 27695
DTB = '/boot/rk3399-firefly-batocera-emmc.dtb'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def image_hash(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def fat_read(image, name):
    return subprocess.check_output(['mtype', '-i', f'{image}@@{FAT_OFFSET}', '::' + name])


def repair(source, destination):
    info = source.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size != RAW_SIZE:
        raise ValueError('input must be the raw direct eMMC test1 image (regular file)')
    if os.path.lexists(destination):
        raise ValueError('output already exists; choose a new file')
    if image_hash(source) != RAW_TEST1:
        raise ValueError('input SHA-256 differs from the direct eMMC release')
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='.vsel1-') as work:
        staged = Path(work) / 'emmc.img'
        subprocess.run(['cp', '--reflink=auto', '--sparse=always', '--', source, staged], check=True)
        if image_hash(staged) != RAW_TEST1:
            raise ValueError('copy differs from the direct eMMC release')
        conf = fat_read(staged, '/extlinux/extlinux.conf')
        if f'  FDT {DTB}'.encode() not in conf or b'dev=/dev/mmcblk2p1' not in conf:
            raise ValueError('unexpected boot target in extlinux')
        old = fat_read(staged, DTB)
        if sha(old) != DTB_TEST1 or old[BANK_OFFSET - 3:BANK_OFFSET + 1] != bytes(4):
            raise ValueError('unexpected starting DTB')
        new = old[:BANK_OFFSET] + b'\1' + old[BANK_OFFSET + 1:]
        if sha(new) != DTB_VSEL1:
            raise ValueError('unexpected corrected DTB')
        with staged.open('r+b') as f:
            f.seek(DTB_OFFSET)
            if f.read(len(old)) != old:
                raise ValueError('DTB is not at the expected offset')
            f.seek(DTB_OFFSET + BANK_OFFSET)
            f.write(b'\1')
            f.flush()
            os.fsync(f.fileno())
        if fat_read(staged, DTB) != new or fat_read(staged, '/extlinux/extlinux.conf') != conf:
            raise ValueError('boot partition readback differs')
        digest = image_hash(staged)
        if digest != RAW_VSEL1:
            raise ValueError('unexpected corrected whole-image SHA-256')
        os.link(staged, destination)
    return digest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('emmc_test1_raw', type=Path)
    p.add_argument('new_emmc_raw', type=Path)
    a = p.parse_args()
    try:
        digest = repair(a.emmc_test1_raw, a.new_emmc_raw)
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        p.exit(1, f'{e}\n')
    print(f'{digest}  {a.new_emmc_raw.name}')


if __name__ == '__main__':
    main()
