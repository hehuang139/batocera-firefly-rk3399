#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Zero only free FAT32 clusters in a regular Firefly Batocera image file.

No partition, FAT entry, allocated cluster, or SHARE byte is changed. This tool
accepts only the known Batocera40 partition/BPB geometry. It never opens block
devices. --check-only inspects allocation; --verify checks that free data is zero.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import struct

SECTOR = 512
PARTITION = (0x0C, 32768, 8388608)
BPB = (512, 8, 32, 2, 8388576, 8176)
ZERO = bytes(8 * 1024 * 1024)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read_at(fd, offset, size):
    result = os.pread(fd, size, offset)
    require(len(result) == size, f'Short read at {offset}')
    return result


def layout(fd, size):
    mbr = read_at(fd, 0, SECTOR)
    require(mbr[510:512] == b'\x55\xaa', 'Invalid MBR signature')
    entry = mbr[446:462]
    part_type = entry[4]
    lba, sectors = struct.unpack_from('<II', entry, 8)
    require((part_type, lba, sectors) == PARTITION, 'Unexpected first partition')
    start, end = lba * SECTOR, (lba + sectors) * SECTOR
    require(size >= end and size % SECTOR == 0, 'Image does not contain the partition')
    boot = read_at(fd, start, SECTOR)
    require(boot[510:512] == b'\x55\xaa' and boot[82:90] == b'FAT32   ', 'Not FAT32')
    require(boot[71:82].rstrip() == b'BATOCERA', 'Unexpected FAT volume label')
    bps = struct.unpack_from('<H', boot, 11)[0]
    spc = boot[13]
    reserved = struct.unpack_from('<H', boot, 14)[0]
    fats = boot[16]
    total, fat_sectors = struct.unpack_from('<II', boot, 32)
    require((bps, spc, reserved, fats, total, fat_sectors) == BPB, 'Unexpected FAT32 BPB')
    require(struct.unpack_from('<H', boot, 17)[0] == 0
            and struct.unpack_from('<H', boot, 19)[0] == 0
            and struct.unpack_from('<H', boot, 22)[0] == 0, 'Conflicting FAT16 fields')
    flags, version = struct.unpack_from('<HH', boot, 40)
    require(not flags & 0x80 and version == 0, 'FAT mirroring/version is unsupported')
    fat_start = start + reserved * bps
    fat_size = fat_sectors * bps
    data_start = fat_start + fats * fat_size
    cluster_size = bps * spc
    cluster_count = (total - reserved - fats * fat_sectors) // spc
    data_end = data_start + cluster_count * cluster_size
    require(data_start < data_end <= start + total * bps <= end, 'FAT data exceeds its partition')
    require(fat_size // 4 >= cluster_count + 2, 'FAT cannot describe all data clusters')
    fat = read_at(fd, fat_start, fat_size)
    require(fat == read_at(fd, fat_start + fat_size, fat_size), 'The two FAT copies differ')
    root_cluster = struct.unpack_from('<I', boot, 44)[0]
    require(2 <= root_cluster <= cluster_count + 1, 'Root directory is outside data clusters')
    require(struct.unpack_from('<I', fat, root_cluster * 4)[0] & 0x0fffffff,
            'Root directory cluster is marked free')
    runs = []
    first = None
    for cluster in range(2, cluster_count + 2):
        free = (struct.unpack_from('<I', fat, cluster * 4)[0] & 0x0fffffff) == 0
        if free and first is None:
            first = cluster
        elif not free and first is not None:
            runs.append((data_start + (first - 2) * cluster_size, (cluster - first) * cluster_size))
            first = None
    if first is not None:
        runs.append((data_start + (first - 2) * cluster_size,
                     (cluster_count + 2 - first) * cluster_size))
    require(all(data_start <= offset < offset + length <= data_end for offset, length in runs),
            'Free run exceeds FAT data bounds')
    info = {'partition_start': start, 'partition_bytes': sectors * SECTOR,
            'bpb_volume_bytes': total * bps, 'cluster_bytes': cluster_size,
            'data_clusters': cluster_count, 'free_runs': len(runs),
            'free_bytes': sum(length for _, length in runs),
            'fat_sha256': hashlib.sha256(fat).hexdigest()}
    return runs, info


def protected_hash(fd, size, runs):
    """Hash every byte outside free runs, including allocated clusters and SHARE."""
    digest = hashlib.sha256()
    cursor = 0
    for offset, length in runs + [(size, 0)]:
        while cursor < offset:
            count = min(len(ZERO), offset - cursor)
            digest.update(read_at(fd, cursor, count))
            cursor += count
        cursor = offset + length
    return digest.hexdigest()


def verify_zero(fd, runs):
    for offset, length in runs:
        stop = offset + length
        while offset < stop:
            count = min(len(ZERO), stop - offset)
            require(read_at(fd, offset, count) == ZERO[:count], f'Nonzero free cluster data at {offset}')
            offset += count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check-only', action='store_true', help='Inspect allocation without writing')
    mode.add_argument('--verify', action='store_true', help='Read-only check that every free cluster is zero')
    args = parser.parse_args()
    before_open = args.image.lstat()
    require(stat.S_ISREG(before_open.st_mode) and args.image.suffix == '.img',
            'Expected an existing regular .img file, not a symlink or device')
    readonly = args.check_only or args.verify
    fd = os.open(args.image, (os.O_RDONLY if readonly else os.O_RDWR) | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, (fcntl.LOCK_SH if readonly else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        opened = os.fstat(fd)
        require(stat.S_ISREG(opened.st_mode)
                and (opened.st_dev, opened.st_ino) == (before_open.st_dev, before_open.st_ino),
                'Image changed while opening')
        size = opened.st_size
        runs, report = layout(fd, size)
        report.update({'image': str(args.image), 'mode': 'check' if args.check_only else 'verify' if args.verify else 'zero'})
        if not readonly:
            before = protected_hash(fd, size, runs)
            for offset, length in runs:
                stop = offset + length
                while offset < stop:
                    block = ZERO[:min(len(ZERO), stop - offset)]
                    written = os.pwrite(fd, block, offset)
                    require(written > 0, f'Short write at {offset}')
                    offset += written
            os.fsync(fd)
            require(os.fstat(fd).st_size == size, 'Image size changed')
            # Re-read both FATs and BPB before trusting the same free cluster map.
            after_runs, after_info = layout(fd, size)
            require(after_runs == runs and after_info == {key: report[key] for key in after_info},
                    'FAT allocation or metadata changed')
            after = protected_hash(fd, size, runs)
            require(before == after, 'Bytes outside free clusters changed')
            report.update({'protected_sha256_before': before, 'protected_sha256_after': after})
        if not args.check_only:
            verify_zero(fd, runs)
            report['all_free_clusters_zero'] = True
        report['result'] = 'PASS'
        print(json.dumps(report, indent=2))
    finally:
        os.close(fd)


if __name__ == '__main__':
    main()
