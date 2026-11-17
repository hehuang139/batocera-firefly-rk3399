#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Independent, read-only inspection of the final Firefly RK3399 disk image.

Run inside the builder container for mtools, fdtget and unsquashfs. Only the
report and a temporary extraction directory are written; the image is read-only.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
SECTOR = 512
EXPECTED_SIZE = 4580179968
EXPECTED_PARTITIONS = [(0x0C, 32768, 8388608), (0x83, 8421376, 524288)]
checks = []


def check(name, ok, detail):
    item = {'name': name, 'pass': bool(ok), 'detail': detail}
    checks.append(item)
    if not ok:
        raise RuntimeError(f'{name}: {detail}')


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def read_at(stream, offset, length):
    stream.seek(offset)
    value = stream.read(length)
    if len(value) != length:
        raise RuntimeError(f'Short image read at {offset}: {len(value)} != {length}')
    return value


def run(arguments):
    return subprocess.check_output(arguments, text=True, stderr=subprocess.STDOUT).strip()


def dtprop(dtb, node, prop, kind='s'):
    return run(['fdtget', '-t', kind, str(dtb), node, prop])


def main(args):
    image = args.image.resolve()
    compressed = args.gzip.resolve() if args.gzip else Path(str(image) + '.gz')
    check('disk-size', image.stat().st_size == EXPECTED_SIZE, image.stat().st_size)
    image_hash = digest(image)
    sidecar = image.with_suffix('.manifest.json')
    declared = json.loads(sidecar.read_text())
    check('sidecar-image-name', declared.get('image') == image.name, declared.get('image'))
    check('sidecar-image-hash', declared.get('sha256') == image_hash, image_hash)
    with image.open('rb') as stream:
        mbr = read_at(stream, 0, 512)
        check('mbr-signature', mbr[510:512] == b'\x55\xaa', mbr[510:512].hex())
        partitions = []
        for index in range(4):
            entry = mbr[446 + index * 16:462 + index * 16]
            bootable, part_type = entry[0], entry[4]
            start, count = struct.unpack_from('<II', entry, 8)
            if index < 2:
                check(f'partition-{index + 1}', (part_type, start, count) == EXPECTED_PARTITIONS[index],
                      {'type': part_type, 'start_lba': start, 'sectors': count})
                check(f'partition-{index + 1}-boot-flag', bootable in (0, 0x80), bootable)
                partitions.append((start * SECTOR, count * SECTOR))
            else:
                check(f'partition-{index + 1}-empty', entry == bytes(16), entry.hex())
        p1_start, p1_size = partitions[0]
        p2_start, p2_size = partitions[1]
        check('partition-boundaries', p1_start + p1_size == p2_start and p2_start + p2_size == EXPECTED_SIZE,
              'Contiguous partitions fit exactly inside the image')
        extents = [(0, SECTOR, 'MBR')]
        boot_payloads = {}
        for name, offset in [('idbloader.img', 32768), ('u-boot.itb', 8388608)]:
            asset = ROOT / 'work/boot/assets' / name
            expected = asset.read_bytes()
            actual = read_at(stream, offset, len(expected))
            boot_payloads[name] = actual
            check('boot-bytes:' + name, actual == expected,
                  {'offset': offset, 'size': len(actual), 'sha256': hashlib.sha256(actual).hexdigest()})
            extents.append((offset, offset + len(actual), name))
        extents.append((p1_start, p1_start + p1_size, 'FAT32'))
        extents.sort()
        check('boot-components-do-not-overlap', all(a[1] <= b[0] for a, b in zip(extents, extents[1:])), extents)
        for preceding, following in zip(extents, extents[1:]):
            gap = read_at(stream, preceding[1], following[0] - preceding[1])
            check('cleared-boot-gap:' + preceding[2] + ':' + following[2], not any(gap),
                  {'start': preceding[1], 'bytes': len(gap), 'purpose': 'No donor loader or saved environment remains'})
        boot_sector = read_at(stream, p1_start, 512)
        check('fat32-signature', boot_sector[510:512] == b'\x55\xaa' and boot_sector[82:90] == b'FAT32   ',
              boot_sector[82:90].decode('ascii', errors='replace'))
        bps = struct.unpack_from('<H', boot_sector, 11)[0]
        total_sectors = struct.unpack_from('<I', boot_sector, 32)[0]
        slack = p1_size - total_sectors * bps
        check('fat32-geometry', bps == 512 and total_sectors == 8388576 and slack == 16384,
              {'bytes_per_sector': bps, 'total_sectors': total_sectors,
               'partition_tail_padding_bytes': slack,
               'reference': 'Official base.img BPB has 32 sectors of partition tail padding'})
        check('fat32-tail-padding-zero', not any(read_at(stream, p1_start + total_sectors * bps, slack)),
              f'{slack} bytes')
        check('fat32-label', boot_sector[71:82].rstrip() == b'BATOCERA', boot_sector[71:82].decode('ascii'))
        superblock = read_at(stream, p2_start + 1024, 1024)
        check('share-ext4-magic', superblock[56:58] == b'\x53\xef', superblock[56:58].hex())
        check('share-label', superblock[120:136].rstrip(b'\0') == b'SHARE',
              superblock[120:136].rstrip(b'\0').decode('ascii'))

    config = (ROOT / 'source/boot/built.config').read_text().splitlines()
    check('boot-env-does-not-use-mmc', 'CONFIG_ENV_IS_NOWHERE=y' in config
          and '# CONFIG_ENV_IS_IN_MMC is not set' in config, 'Built config uses memory-only environment')
    check('boot-video-disabled', '# CONFIG_VIDEO is not set' in config, 'Linux owns display setup')
    bootbin = (ROOT / 'work/boot/uboot/u-boot.bin').read_bytes()
    check('boot-targets-tf-only', b'boot_targets=mmc1\0' in bootbin, 'mmc1')
    spl_dtb = ROOT / 'work/boot/uboot/spl/u-boot-spl.dtb'
    check('spl-loads-tf-only', dtprop(spl_dtb, '/chosen', 'u-boot,spl-boot-order') == '/mmc@fe320000',
          '/mmc@fe320000')
    compiled_spl = (ROOT / 'work/boot/uboot/spl/u-boot-spl.bin').read_bytes()
    compiled_tpl = (ROOT / 'work/boot/uboot/tpl/u-boot-tpl.bin').read_bytes()
    compiled_uboot = (ROOT / 'work/boot/uboot/u-boot-nodtb.bin').read_bytes()
    compiled_uboot_dtb = (ROOT / 'work/boot/uboot/u-boot.dtb').read_bytes()
    idb = boot_payloads['idbloader.img']
    check('disk-idb-contains-compiled-spl', compiled_spl in idb,
          'Embedded SPL matches the build whose SD-only DTB was inspected')
    check('disk-idb-contains-compiled-tpl', idb[2048:2052] == b'RK33'
          and idb[2052:2048 + len(compiled_tpl)] == compiled_tpl[4:],
          'Embedded TPL matches DDR3 build, with standard RK33 marker')
    check('disk-fit-contains-compiled-uboot', compiled_uboot in boot_payloads['u-boot.itb'],
          'Embedded executable matches the inspected boot environment')
    check('disk-fit-contains-control-dtb', compiled_uboot_dtb in boot_payloads['u-boot.itb'],
          'Embedded Firefly control DTB matches the build')

    temp_parent = ROOT / 'work/verify-image'
    temp_parent.mkdir(parents=True, exist_ok=True)
    scratch = args.scratch or temp_parent
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='readback-', dir=scratch) as temporary:
        temporary = Path(temporary)

        def extract(remote):
            relative = PurePosixPath(remote.lstrip('/'))
            if '..' in relative.parts or not relative.parts:
                raise ValueError(f'Invalid FAT path: {remote}')
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            run(['mcopy', '-i', f'{image}@@{p1_start}', '::/' + str(relative), str(target)])
            return target

        extlinux = extract('extlinux/extlinux.conf')
        text = extlinux.read_text()
        values = {}
        for line in text.splitlines():
            tokens = line.strip().split(None, 1)
            if len(tokens) == 2 and tokens[0] in {'LINUX', 'INITRD', 'FDT', 'APPEND'}:
                check('single-extlinux-' + tokens[0].lower(), tokens[0] not in values, tokens[1])
                values[tokens[0]] = tokens[1]
        expected_paths = {'LINUX': '/boot/linux', 'INITRD': '/boot/initrd.lz4',
                          'FDT': '/boot/rk3399-firefly-batocera-sd.dtb'}
        for key, expected in expected_paths.items():
            check('extlinux-' + key.lower(), values.get(key) == expected, values.get(key))
        append_tokens = values.get('APPEND', '').split()
        check('extlinux-root-pinned-to-tf', 'dev=/dev/mmcblk1p1' in append_tokens,
              values.get('APPEND'))
        check('extlinux-no-ambiguous-label', not any(token.startswith('label=') for token in append_tokens),
              'The initrd is directed at mmc1 TF; another BATOCERA-labelled USB disk cannot select the root')
        check('extlinux-serial', 'console=ttyS2,1500000n8' in values.get('APPEND', '').split(), values.get('APPEND'))
        for key in ['LINUX', 'INITRD']:
            item = extract(values[key])
            baseline = ROOT / 'work/base-boot' / values[key].lstrip('/')
            check('unchanged-' + key.lower(), digest(item) == digest(baseline),
                  {'bytes': item.stat().st_size, 'sha256': digest(item)})
        dtb = extract(values['FDT'])
        check('dtb-matches-build', digest(dtb) == digest(ROOT / 'work/kernel/rk3399-firefly-batocera-sd.dtb'), digest(dtb))
        properties = [
            ('/', 'model', 'Firefly-RK3399 Board', 's'),
            ('/', 'compatible', 'firefly,firefly-rk3399 rockchip,rk3399', 's'),
            ('/aliases', 'mmc1', '/mmc@fe320000', 's'),
            ('/mmc@fe320000', 'status', 'okay', 's'),
            ('/mmc@fe330000', 'status', 'disabled', 's'),
            ('/syscon@ff770000/phy@f780', 'status', 'disabled', 's'),
            ('/hdmi@ff940000', 'status', 'okay', 's'),
            ('/hdmi-sound', 'status', 'okay', 's'),
            ('/gpu@ff9a0000', 'status', 'okay', 's'),
            ('/ethernet@fe300000', 'status', 'okay', 's'),
            ('/thermal-zones/cpu-thermal/trips/cpu_crit', 'temperature', '95000', 'u'),
        ]
        for node, prop, expected, kind in properties:
            actual = dtprop(dtb, node, prop, kind)
            check('image-dtb:' + node + ':' + prop, actual == expected, actual)
        board = extract('boot/batocera.board').read_text().strip()
        check('board-identity', board == 'firefly-rk3399', board)
        squashfs = extract('boot/batocera')
        with squashfs.open('rb') as stream:
            check('squashfs-magic', stream.read(4) == b'hsqs', 'little-endian SquashFS')
        squashfs_stat = run(['unsquashfs', '-s', str(squashfs)])
        check('squashfs-superblock', 'Compression zstd' in squashfs_stat, squashfs_stat)
        # Pseudo-file export reads every inode and regular-file data block,
        # unlike a directory listing, without needing root or special nodes.
        with (temp_parent / 'squashfs-readback.log').open('w') as log:
            process = subprocess.run(['unsquashfs', '-no-progress', '-processors', '2',
                                      '-pf', '/dev/null', str(squashfs)],
                                     stdout=log, stderr=subprocess.STDOUT)
        check('squashfs-full-decompression', process.returncode == 0,
              (temp_parent / 'squashfs-readback.log').read_text()[-4000:])
        sq_hash = digest(squashfs)
        check('squashfs-matches-assembly-manifest', sq_hash == declared.get('rootfs_sha256'),
              {'actual': sq_hash, 'declared': declared.get('rootfs_sha256')})

    compressed_hash = None
    if not args.skip_gzip:
        decompressed_hash = hashlib.sha256()
        decompressed_bytes = 0
        with gzip.open(compressed, 'rb') as stream:
            for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                decompressed_hash.update(chunk)
                decompressed_bytes += len(chunk)
        check('gzip-roundtrip', decompressed_bytes == EXPECTED_SIZE and decompressed_hash.hexdigest() == image_hash,
              {'decompressed_bytes': decompressed_bytes, 'sha256': decompressed_hash.hexdigest()})
        compressed_hash = digest(compressed)

    sums_file = image.parent / 'SHA256SUMS'
    check('checksum-file-present', sums_file.is_file(), sums_file.name)
    sums = {}
    for line in sums_file.read_text().splitlines():
        if not line.strip():
            continue
        value, name = line.split(None, 1)
        sums[name.lstrip('*')] = value
    for path, value in [(image, image_hash)] + ([] if args.skip_gzip else [(compressed, compressed_hash)]):
        check('published-checksum:' + path.name, sums.get(path.name) == value, value)
    return {'image': str(image), 'image_sha256': image_hash,
            'compressed': None if args.skip_gzip else str(compressed),
            'compressed_sha256': compressed_hash, 'system_squashfs_sha256': sq_hash,
            'gzip_checked': not args.skip_gzip}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, default=ROOT / 'outputs/batocera40-firefly-rk3399-sd-test1.img')
    parser.add_argument('--gzip', type=Path)
    parser.add_argument('--skip-gzip', action='store_true', help='Only inspect raw image before compression is ready')
    parser.add_argument('--scratch', type=Path, help='Temporary extraction directory, preferably on an SSD')
    parser.add_argument('--report', type=Path, default=ROOT / 'work/verify-image/report.json')
    args = parser.parse_args()
    result = {}
    try:
        result.update(main(args))
    except Exception as error:
        result['error'] = f'{type(error).__name__}: {error}'
    result.update({'checks': checks, 'passed': sum(item['pass'] for item in checks), 'total': len(checks),
                   'result': 'FAIL' if 'error' in result else 'PASS'})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(f"Image verification: {result['passed']}/{result['total']} {result['result']}")
    if 'error' in result:
        print(result['error'])
        raise SystemExit(1)
