#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Copy the exact 43.1 TF installer test1 and repair both levels of Linux DTB."""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile

spec = importlib.util.spec_from_file_location('emmc', Path(__file__).with_name('repair-emmc-vsel.py'))
emmc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(emmc)
TF_SIZE = 6727663616
TF_TEST1 = 'a40d9a8cd00dd31414c8790789a8cbe52982f7fce8b23668aa54ba8654e2289b'
SHARE_OFFSET = 12615680 * 512
EXTLINUX = '/extlinux/extlinux.conf'
MANIFEST = '/emmc/manifest.json'
INSTALLER = '/emmc/install-to-emmc.py'
EMMC_NAME = 'batocera431-firefly-rk3399-emmc-test1.img'
PAYLOAD = '/emmc/' + EMMC_NAME + '.gz'
SCRIPT_SHA = 'f1e62933d3696562a0738a38c0978949ee767e0812b3f311366f547ed185266b'
OLD_PAYLOAD = {'name': EMMC_NAME + '.gz', 'bytes': 2230172458,
               'sha256': 'a492451773f926b417911aed8f792f56c169f36da97251befdca65a7e74df771'}
UPDATED = {emmc.DTB, MANIFEST, PAYLOAD}


def fat_cmd(command, image, *args):
    return [command, '-i', f'{image}@@{emmc.FAT_OFFSET}', *args]


def digest_stream(stream):
    h, size = hashlib.sha256(), 0
    for chunk in iter(lambda: stream.read(8 << 20), b''):
        h.update(chunk)
        size += len(chunk)
    return size, h.hexdigest()


def fat_digest(image, name):
    with subprocess.Popen(fat_cmd('mtype', image, '::' + name), stdout=subprocess.PIPE) as proc:
        result = digest_stream(proc.stdout)
        if proc.wait():
            raise ValueError(f'failed to read FAT file {name}')
    return result


def listing(image):
    names = subprocess.check_output(fat_cmd('mdir', image, '-b', '-s', '::/')).decode('ascii').splitlines()
    if any(not name.startswith('::/') for name in names):
        raise ValueError('unexpected FAT listing')
    return {name[2:] for name in names if not name.endswith('/')}


def region_digest(image, offset, length):
    h = hashlib.sha256()
    with image.open('rb') as f:
        f.seek(offset)
        while length:
            block = f.read(min(length, 8 << 20))
            if not block:
                raise ValueError('truncated image region')
            h.update(block)
            length -= len(block)
    return h.hexdigest()


def check_source(source):
    info = source.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size != TF_SIZE or emmc.image_hash(source) != TF_TEST1:
        raise ValueError('input must be the exact raw TF installer test1 (regular file)')
    def read(name):
        return emmc.fat_read(source, name)
    expected = {'board': 'firefly-rk3399', 'medium': 'emmc', 'compressed': OLD_PAYLOAD,
                'image': {'name': EMMC_NAME, 'bytes': emmc.RAW_SIZE, 'sha256': emmc.RAW_TEST1}}
    conf = read(EXTLINUX)
    if (f'  FDT {emmc.DTB}'.encode() not in conf or b'dev=/dev/mmcblk1p1' not in conf
            or emmc.sha(read(emmc.DTB)) != emmc.DTB_TEST1 or emmc.sha(read(INSTALLER)) != SCRIPT_SHA
            or json.loads(read(MANIFEST)) != expected):
        raise ValueError('unexpected TF boot entry, DTB, installer, or manifest')
    if fat_digest(source, PAYLOAD) != (OLD_PAYLOAD['bytes'], OLD_PAYLOAD['sha256']):
        raise ValueError('original embedded payload differs from test1')
    return expected


def check_output(source, output, payload_meta):
    if output.stat().st_size != TF_SIZE or listing(source) != listing(output):
        raise ValueError('TF geometry or file list changed')
    for name in listing(source) - UPDATED:
        if fat_digest(source, name) != fat_digest(output, name):
            raise ValueError(f'unexpected FAT change: {name}')
    for offset, length in [(0, emmc.FAT_OFFSET), (SHARE_OFFSET, TF_SIZE - SHARE_OFFSET)]:
        if region_digest(source, offset, length) != region_digest(output, offset, length):
            raise ValueError('bootloader or SHARE changed')
    if emmc.sha(emmc.fat_read(output, emmc.DTB)) != emmc.DTB_VSEL1:
        raise ValueError('TF boot DTB does not match the corrected DTB')
    if json.loads(emmc.fat_read(output, MANIFEST)) != payload_meta:
        raise ValueError('embedded manifest readback differs')
    meta = payload_meta['compressed']
    if fat_digest(output, PAYLOAD) != (meta['bytes'], meta['sha256']):
        raise ValueError('embedded eMMC gzip differs from the verified payload')


def repair(source, payload, destination):
    if os.path.lexists(destination):
        raise ValueError('output already exists; choose a new file')
    meta = check_source(source)
    info = payload.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('eMMC gzip input must be a regular file')
    with gzip.open(payload, 'rb') as gz:
        if digest_stream(gz) != (emmc.RAW_SIZE, emmc.RAW_VSEL1):
            raise ValueError('eMMC gzip must decompress to the corrected eMMC image')
    meta['image']['sha256'] = emmc.RAW_VSEL1
    meta['compressed'].update(bytes=info.st_size, sha256=emmc.image_hash(payload))
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='.vsel1-tf-') as name:
        work = Path(name)
        staged = work / 'installer.img'
        subprocess.run(['cp', '--reflink=auto', '--sparse=always', '--', source, staged], check=True)
        if emmc.image_hash(staged) != TF_TEST1:
            raise ValueError('copy differs from the TF installer test1')
        old = emmc.fat_read(staged, emmc.DTB)
        cpu_bank = emmc.BANK_OFFSET
        if old[cpu_bank - 3:cpu_bank + 1] != bytes(4):
            raise ValueError('unexpected original CPU selector')
        dtb = work / 'fixed.dtb'
        dtb.write_bytes(old[:cpu_bank] + b'\1' + old[cpu_bank + 1:])
        manifest = work / 'manifest.json'
        manifest.write_text(json.dumps(meta, indent=2) + '\n', encoding='ascii')
        subprocess.run(fat_cmd('mdel', staged, '::' + PAYLOAD), check=True)
        for local, target in [(dtb, emmc.DTB), (manifest, MANIFEST), (payload, PAYLOAD)]:
            subprocess.run(fat_cmd('mcopy', staged, '-m', '-o', local, '::' + target), check=True)
        check_output(source, staged, meta)
        digest = emmc.image_hash(staged)
        os.link(staged, destination)
    return digest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('tf_test1_raw', type=Path)
    p.add_argument('fixed_emmc_gzip', type=Path)
    p.add_argument('new_tf_raw', type=Path)
    a = p.parse_args()
    try:
        digest = repair(a.tf_test1_raw, a.fixed_emmc_gzip, a.new_tf_raw)
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        p.exit(1, f'{e}\n')
    print(f'{digest}  {a.new_tf_raw.name}')


if __name__ == '__main__':
    main()
