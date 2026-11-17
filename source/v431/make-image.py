#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Assemble Firefly RK3399 Batocera 43.1 images using ordinary files only."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
START = 32768
SHARE_SECTORS = 524288
FAT_SECTORS = {'emmc': 8388608, 'installer': 12582912}
NAMES = {'emmc': 'batocera431-firefly-rk3399-emmc-test1.img',
         'installer': 'batocera431-firefly-rk3399-emmc-installer-tf-test1.img'}


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8388608), b''):
            h.update(block)
    return h.hexdigest()


def regular(path):
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('Expected an ordinary file: ' + str(path))


def check_pinned(path, expected):
    regular(path)
    if path.stat().st_size != expected['bytes'] or sha(path) != expected['sha256']:
        raise ValueError('Input checksum mismatch: ' + str(path))


def run(args):
    subprocess.run([str(x) for x in args], check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=NAMES)
    p.add_argument('rootfs', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--payload', type=Path)
    p.add_argument('--payload-manifest', type=Path)
    p.add_argument('--inputs', type=Path, default=HERE / 'inputs.json')
    a = p.parse_args()
    sidecar = a.output.with_suffix('.manifest.json')
    for path in (a.output, sidecar):
        if path.exists() or path.is_symlink():
            raise ValueError('Refusing to overwrite: ' + str(path))
    if a.output.name != NAMES[a.mode]:
        raise ValueError('Use the fixed release filename: ' + NAMES[a.mode])
    regular(a.inputs)
    inputs = json.loads(a.inputs.read_text())
    check_pinned(a.rootfs, inputs['rootfs'])
    components = inputs['components']
    if components['share']['bytes'] != SHARE_SECTORS * 512:
        raise ValueError('SHARE input must exactly match the declared partition')
    for item in components.values():
        check_pinned(ROOT / item['path'], item)
    boot = inputs['boot_assets'][a.mode]
    for item in boot.values():
        check_pinned(ROOT / item['path'], item)
    docs = inputs['documents']
    for item in docs.values():
        check_pinned(ROOT / item['path'], item)
    payload = None
    if a.mode == 'installer':
        if not a.payload or not a.payload_manifest:
            p.error('Installer requires --payload and --payload-manifest')
        regular(a.payload_manifest)
        payload = json.loads(a.payload_manifest.read_text())
        if (payload.get('board') != 'firefly-rk3399' or payload.get('medium') != 'emmc'
                or payload['image']['name'] != NAMES['emmc']
                or payload['image']['bytes'] != (START + FAT_SECTORS['emmc'] + SHARE_SECTORS) * 512
                or payload['compressed']['name'] != NAMES['emmc'] + '.gz'
                or a.payload.name != payload['compressed']['name']):
            raise ValueError('Wrong eMMC payload identity')
        check_pinned(a.payload, payload['compressed'])
        payload_sidecar = a.payload.with_suffix('').with_suffix('.manifest.json')
        regular(payload_sidecar)
        built = json.loads(payload_sidecar.read_text())
        if (built.get('release') != '43.1-firefly-emmc-test1' or built.get('mode') != 'emmc'
                or built.get('sha256') != payload['image']['sha256']
                or built.get('bytes') != payload['image']['bytes']
                or built.get('rootfs_sha256') != inputs['rootfs']['sha256']):
            raise ValueError('Payload build does not match this 43.1 release')
    sectors = FAT_SECTORS[a.mode]
    share_start = START + sectors
    image_bytes = (share_start + SHARE_SECTORS) * 512
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='assemble-', dir=a.output.parent) as scratch:
        scratch = Path(scratch)
        fat = scratch / 'boot.fat'
        with fat.open('xb') as stream:
            stream.truncate(sectors * 512)
        run(['mkfs.vfat', '-F', '32', '-S', '512', '-s', '8', '-R', '32',
             '-n', 'BATOCERA', '-i', '43133990', fat])

        def copy(source, destination):
            run(['mcopy', '-o', '-i', fat, source, '::/' + destination])

        for name in ['boot', 'extlinux'] + (['emmc'] if payload else []):
            run(['mmd', '-i', fat, '::/' + name])
        for key, destination in [('kernel', 'boot/linux'), ('initrd', 'boot/initrd.lz4'),
                                 ('secondary', 'boot/rufomaculata'),
                                 ('dtb', 'boot/rk3399-firefly-batocera-emmc.dtb'),
                                 ('board', 'boot/batocera.board'),
                                 ('boot_config', 'batocera-boot.conf'),
                                 ('collect_logs', 'collect-logs.sh')]:
            copy(ROOT / components[key]['path'], destination)
        copy(a.rootfs, 'boot/batocera')
        copy(ROOT / boot['extlinux']['path'], 'extlinux/extlinux.conf')
        for key, destination in [('install', 'FIREFLY-README.txt'), ('hotkey', 'SELECT-HOTKEY.txt')]:
            copy(ROOT / docs[key]['path'], destination)
        if payload:
            copy(a.payload, 'emmc/' + a.payload.name)
            copy(a.payload_manifest, 'emmc/manifest.json')
            copy(ROOT / components['installer']['path'], 'emmc/install-to-emmc.py')
        run(['fsck.vfat', '-n', fat])
        mbr = bytearray(512)
        for index, (kind, start, count) in enumerate([(12, START, sectors),
                                                     (131, share_start, SHARE_SECTORS)]):
            # LBA is authoritative; saturated CHS values avoid obsolete geometry assumptions.
            entry = struct.pack('<B3sB3sII', 0, b'\xfe\xff\xff', kind,
                                b'\xfe\xff\xff', start, count)
            mbr[446 + index * 16:462 + index * 16] = entry
        mbr[510:] = b'\x55\xaa'
        with a.output.open('xb') as stream:
            stream.truncate(image_bytes)
            stream.seek(0)
            stream.write(mbr)
            for key, offset, limit in [('idbloader', 32768, 8388608),
                                       ('uboot', 8388608, START * 512)]:
                item = boot[key]
                if offset + item['bytes'] > limit:
                    raise ValueError('Bootloader overlaps the next image region')
                stream.seek(offset)
                stream.write((ROOT / item['path']).read_bytes())
            stream.seek(START * 512)
            with fat.open('rb') as source:
                shutil.copyfileobj(source, stream, 8388608)
            stream.seek(share_start * 512)
            with (ROOT / components['share']['path']).open('rb') as source:
                shutil.copyfileobj(source, stream, 8388608)
    report = {'release': '43.1-firefly-emmc-test1', 'image': a.output.name,
              'mode': a.mode, 'board': 'firefly-rk3399', 'version': '43.1', 'hotkey': 'select',
              'bytes': image_bytes, 'sha256': sha(a.output),
              'root_device': '/dev/mmcblk2p1' if a.mode == 'emmc' else '/dev/mmcblk1p1',
              'rootfs_sha256': inputs['rootfs']['sha256'],
              'secondary_sha256': inputs['components']['secondary']['sha256'],
              'inputs_sha256': sha(a.inputs),
              'partitions': [{'type': 12, 'start_lba': START, 'sectors': sectors},
                             {'type': 131, 'start_lba': share_start, 'sectors': SHARE_SECTORS}],
              'boot_assets': boot}
    if payload:
        report['payload'] = payload
        report['installer_script_sha256'] = components['installer']['sha256']
    with sidecar.open('x') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
