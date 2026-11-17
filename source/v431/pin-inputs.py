#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Pin every ordinary-file input used to assemble the 43.1 images."""
import argparse
import hashlib
import json
from pathlib import Path
import stat

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def pin(path):
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('Expected ordinary file: ' + str(path))
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8388608), b''):
            h.update(block)
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size, 'sha256': h.hexdigest()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('rootfs', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    if a.output.exists() or a.output.is_symlink():
        raise ValueError('Refusing to overwrite inputs')
    system = pin(a.rootfs.resolve()) if a.rootfs.resolve().is_relative_to(ROOT) else None
    if system is None:
        # The system staging tree may live on another SSD.
        path = a.rootfs
        if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
            raise ValueError('Expected ordinary SquashFS')
        h = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(8388608), b''): h.update(block)
        system = {'bytes': path.stat().st_size, 'sha256': h.hexdigest()}
    system.pop('path', None)
    files = {'kernel': 'linux', 'initrd': 'initrd.lz4', 'secondary': 'rufomaculata',
             'dtb': 'rk3399-firefly-batocera-emmc.dtb', 'board': 'batocera.board',
             'boot_config': 'batocera-boot.conf', 'collect_logs': 'collect-logs.sh',
             'share': 'share.ext4', 'installer': 'install-to-emmc.py'}
    result = {'version': '43.1', 'rootfs': system,
              'components': {key: pin(HERE / 'assets' / name) for key, name in files.items()},
              'boot_assets': {}, 'documents': {}}
    for mode, base in [('emmc', 'source/emmc/boot-assets'), ('installer', 'source/boot-assets')]:
        result['boot_assets'][mode] = {
            'idbloader': pin(ROOT / base / 'idbloader.img'),
            'uboot': pin(ROOT / base / 'u-boot.itb'),
            'extlinux': pin(HERE / 'assets' / ('extlinux-' + mode + '.conf'))}
    for key, name in [('install', 'eMMC安装说明.md'), ('hotkey', 'Select热键.md')]:
        result['documents'][key] = pin(HERE / 'docs' / name)
    result['rootfs_checks'] = json.loads((HERE / 'verification/rootfs-inputs.json').read_text())
    a.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'rootfs': system, 'components': len(files), 'output': str(a.output)}, indent=2))


if __name__ == '__main__': main()
