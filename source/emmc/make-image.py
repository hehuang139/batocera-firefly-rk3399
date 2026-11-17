#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Derive an eMMC or TF installer image from the verified Firefly SD release."""
import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent
BOOT_OFFSET = 16777216
SIZE = 4580179968


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(8388608), b''):
            h.update(b)
    return h.hexdigest()


def regular(path):
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('Only ordinary files are accepted: '+str(path))


def check_new(path):
    if path.exists() or path.is_symlink():
        raise ValueError('Refusing to overwrite '+str(path))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['emmc', 'installer'])
    p.add_argument('sd_release_gz', type=Path)
    p.add_argument('output_img', type=Path)
    p.add_argument('--payload', type=Path)
    p.add_argument('--payload-manifest', type=Path)
    a = p.parse_args()
    sidecar = a.output_img.with_suffix('.manifest.json')
    check_new(a.output_img)
    check_new(sidecar)
    if a.output_img.suffix != '.img':
        raise ValueError('Output must be a new .img file')
    regular(a.sd_release_gz)
    base = json.loads((HERE/'inputs.json').read_text())
    if a.sd_release_gz.stat().st_size != base['sd_compressed']['bytes'] or sha(a.sd_release_gz) != base['sd_compressed']['sha256']:
        raise ValueError('Firefly SD compressed release checksum mismatch')
    boot_assets = HERE/'boot-assets' if a.mode == 'emmc' else SOURCE/'boot-assets'
    config_assets = HERE/'boot-assets' if a.mode == 'emmc' else HERE/'installer-assets'
    dtb = HERE/'boot-assets/rk3399-firefly-batocera-emmc.dtb'
    doc = HERE/'docs/eMMC安装说明.md'
    for path in [boot_assets/'idbloader.img', boot_assets/'u-boot.itb', dtb,
                 config_assets/'extlinux.conf', doc]:
        regular(path)
    payload_meta = None
    if a.mode == 'installer':
        if not a.payload or not a.payload_manifest:
            p.error('Installer requires --payload and --payload-manifest')
        for path in [a.payload, a.payload_manifest, HERE/'flash/install-to-emmc.py']:
            regular(path)
        payload_meta = json.loads(a.payload_manifest.read_text())
        if payload_meta['board'] != 'firefly-rk3399' or payload_meta['medium'] != 'emmc':
            raise ValueError('Wrong payload board or medium')
        raw = payload_meta['image']
        if (raw.get('bytes') != SIZE or not isinstance(raw.get('name'), str)
                or Path(raw['name']).name != raw['name'] or not raw['name'].endswith('.img')
                or not re.fullmatch(r'[0-9a-f]{64}', raw.get('sha256', ''))):
            raise ValueError('Invalid eMMC raw payload metadata')
        info = payload_meta['compressed']
        if info['name'] != a.payload.name or info['bytes'] != a.payload.stat().st_size or info['sha256'] != sha(a.payload):
            raise ValueError('eMMC compressed payload mismatch')
    h = hashlib.sha256()
    with gzip.open(a.sd_release_gz, 'rb') as src, a.output_img.open('xb') as dst:
        for b in iter(lambda: src.read(8388608), b''):
            dst.write(b)
            h.update(b)
    if a.output_img.stat().st_size != SIZE or h.hexdigest() != base['sd_image']['sha256']:
        raise ValueError('Decompressed Firefly SD release mismatch')
    with a.output_img.open('r+b') as f:
        mbr = f.read(512)
        if mbr[510:] != b'\x55\xaa':
            raise ValueError('Invalid MBR')
        for i, expected in enumerate([(12, 32768, 8388608), (131, 8421376, 524288)]):
            fields = struct.unpack('<B3sB3sII', mbr[446+i*16:462+i*16])
            if (fields[2], fields[4], fields[5]) != expected:
                raise ValueError('Unexpected partition geometry')
        f.seek(512)
        f.write(bytes(BOOT_OFFSET-512))
        for name, offset, limit in [('idbloader.img',32768,8388608), ('u-boot.itb',8388608,BOOT_OFFSET)]:
            data = (boot_assets/name).read_bytes()
            if offset+len(data)>limit:
                raise ValueError('Boot asset overlaps next region')
            f.seek(offset)
            f.write(data)
    drive = f'{a.output_img}@@{BOOT_OFFSET}'
    def copy(path, dest):
        subprocess.run(['mcopy','-o','-i',drive,str(path),'::/'+dest],check=True)
    copy(dtb,'boot/'+dtb.name)
    copy(config_assets/'extlinux.conf','extlinux/extlinux.conf')
    copy(doc,'FIREFLY-README.txt')
    subprocess.run(['mdel','-i',drive,'::/boot/rk3399-firefly-batocera-sd.dtb'],check=True)
    if a.mode == 'installer':
        subprocess.run(['mmd','-i',drive,'::/emmc'],check=True)
        copy(a.payload,'emmc/'+a.payload.name)
        copy(a.payload_manifest,'emmc/manifest.json')
        copy(HERE/'flash/install-to-emmc.py','emmc/install-to-emmc.py')
    subprocess.run([sys.executable,str(SOURCE/'zero-free-fat.py'),str(a.output_img)],check=True)
    with a.output_img.open('rb') as f:
        if f.read(512)!=mbr:raise ValueError('MBR changed')
    report={'image':a.output_img.name,'mode':a.mode,'board':'firefly-rk3399','bytes':SIZE,
            'sha256':sha(a.output_img),'source_sd_sha256':base['sd_image']['sha256'],
            'rootfs_sha256':base['rootfs_sha256'],'free_fat_clusters_zeroed':True,
            'root_device':'/dev/mmcblk2p1' if a.mode=='emmc' else '/dev/mmcblk1p1',
            'boot_assets':{name:sha(boot_assets/name) for name in ['idbloader.img','u-boot.itb']},
            'dtb_sha256':sha(dtb),'extlinux_sha256':sha(config_assets/'extlinux.conf')}
    if payload_meta:
        report['payload']=payload_meta
        report['installer_script_sha256']=sha(HERE/'flash/install-to-emmc.py')
    with sidecar.open('x') as f:f.write(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
