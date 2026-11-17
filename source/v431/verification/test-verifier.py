#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise real boot assets and malformed metadata using ordinary files only."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location('v431_verifier', HERE.parent / 'verify-image.py')
module = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(module)
cases = []


def case(name, operation, reject=False):
    try:
        operation()
    except (ValueError, RuntimeError, gzip.BadGzipFile, EOFError) as error:
        if not reject:
            raise
        cases.append({'name': name, 'result': 'PASS', 'rejected': str(error)[:300]})
    else:
        if reject:
            raise RuntimeError(name + ' was not rejected')
        cases.append({'name': name, 'result': 'PASS'})


def mbr(mode):
    geometry = module.GEOMETRIES[mode]
    content = bytearray(512)
    for index, item in enumerate([(12, 32768, geometry['fat_sectors']),
                                  (131, 32768 + geometry['fat_sectors'], 524288)]):
        kind, start, sectors = item
        content[446 + 16 * index:462 + 16 * index] = struct.pack('<B3sB3sII', 0, bytes(3), kind, bytes(3), start, sectors)
    content[510:] = b'\x55\xaa'
    return content


def main(output):
    with tempfile.TemporaryDirectory(prefix='verify-v431-fixtures-') as temporary:
        temporary = Path(temporary)
        for mode in module.GEOMETRIES:
            path = temporary / (mode + '.img')
            path.write_bytes(mbr(mode))
            case(mode + '-mbr-valid', lambda: module.verify_mbr(path.open('rb'), mode))
            wrong = mbr(mode)
            struct.pack_into('<I', wrong, 454, 16384)
            path.write_bytes(wrong)
            case(mode + '-wrong-start-rejected', lambda: module.verify_mbr(path.open('rb'), mode), True)
        path = temporary / 'bad.img'
        bad = mbr('emmc')
        bad[510:] = bytes(2)
        path.write_bytes(bad)
        case('invalid-mbr-signature', lambda: module.verify_mbr(path.open('rb'), 'emmc'), True)
        bad = mbr('emmc')
        bad[478] = 1
        path.write_bytes(bad)
        case('extra-partition-rejected', lambda: module.verify_mbr(path.open('rb'), 'emmc'), True)
        init_scratch = temporary / 'initrd'
        init_scratch.mkdir()
        case('actual-initrd-parser', lambda: module.verify_initrd(ROOT / 'source/v431/assets/initrd.lz4', init_scratch))
        for mode in module.GEOMETRIES:
            boot = temporary / ('boot-' + mode + '.img')
            asset = ROOT / ('source/emmc/boot-assets' if mode == 'emmc' else 'source/boot-assets')
            with boot.open('wb') as stream:
                stream.truncate(32768 * 512)
                for name, offset in [('idbloader.img', 32768), ('u-boot.itb', 8388608)]:
                    stream.seek(offset)
                    stream.write((asset / name).read_bytes())
            scratch = temporary / ('scratch-' + mode)
            scratch.mkdir()
            case(mode + '-actual-boot-fit', lambda: module.verify_boot(boot.open('rb'), mode, scratch))
            with boot.open('r+b') as stream:
                stream.seek(32768)
                first = stream.read(1)
                stream.seek(32768)
                stream.write(bytes([first[0] ^ 1]))
            case(mode + '-corrupt-idb-rejected', lambda: module.verify_boot(boot.open('rb'), mode, scratch), True)
        case('parent-path-rejected', lambda: module.relative('boot/../../etc/passwd'), True)
        case('normalized-path-required', lambda: module.relative('boot//batocera'), True)
        content = temporary / 'source'
        content.write_bytes(b'fixture\n')
        expected = {'bytes': 8, 'sha256': hashlib.sha256(content.read_bytes()).hexdigest()}
        case('pinned-source-valid', lambda: module.pinned(content, expected, 'fixture-source'))
        content.write_bytes(b'changed\n')
        case('pinned-source-mismatch', lambda: module.pinned(content, expected, 'fixture-source'), True)
        compressed = temporary / 'content.gz'
        with gzip.open(compressed, 'wb') as stream:
            stream.write(b'fixture contents')
        case('gzip-stream-valid', lambda: module.hash_gzip(compressed))
        compressed.write_bytes(compressed.read_bytes()[:-3])
        case('gzip-truncated-rejected', lambda: module.hash_gzip(compressed), True)
        script = temporary / 'installer.py'
        raw_name = module.GEOMETRIES['emmc']['name']
        script.write_text("p.add_argument('--image', type=Path, default=Path(__file__).parent / " + repr(raw_name + '.gz') + ")\n")
        case('installer-43.1-default-valid', lambda: module.verify_installer_script(script, raw_name))
        script.write_text("p.add_argument('--image', type=Path, default=Path(__file__).parent / 'batocera40-firefly-rk3399-emmc-test1.img.gz')\n")
        case('installer-old-release-default-rejected', lambda: module.verify_installer_script(script, raw_name), True)
        script.write_text("p.add_argument('--manifest', default='manifest.json')\n")
        case('installer-missing-image-default-rejected', lambda: module.verify_installer_script(script, raw_name), True)
    report = {'result': 'PASS', 'count': len(cases), 'cases': cases,
              'verifier_sha256': module.sha(HERE.parent / 'verify-image.py'),
              'scope': 'Ordinary temporary files; real pinned U-Boot FIT/idb assets parsed with fdtget/dumpimage. No block device or board was accessed.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    main(args.report)
