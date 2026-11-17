#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build the Select-hotkey test2 image with the verified eMMC image builder."""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys
from spec import inspect_tree

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent
NAMES = {'emmc': 'batocera40-firefly-rk3399-emmc-test2.img',
         'installer': 'batocera40-firefly-rk3399-emmc-installer-tf-test2.img'}


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8388608), b''):
            result.update(chunk)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=NAMES)
    parser.add_argument('sd_release_gz', type=Path)
    parser.add_argument('output_img', type=Path)
    parser.add_argument('--payload', type=Path)
    parser.add_argument('--payload-manifest', type=Path)
    args = parser.parse_args()
    if args.output_img.name != NAMES[args.mode]:
        raise ValueError('Use the fixed test2 image name: ' + NAMES[args.mode])
    overlay = HERE / 'assets/overlay'
    manifest_path = HERE / 'assets/overlay-manifest.json'
    for path in (overlay, manifest_path, HERE / 'docs/Select热键.md', HERE / 'docs/eMMC安装说明.md'):
        if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
            raise ValueError('Expected an ordinary file: ' + str(path))
    manifest = json.loads(manifest_path.read_text())
    if overlay.stat().st_size != manifest['image']['bytes'] or digest(overlay) != manifest['image']['sha256']:
        raise ValueError('Saved overlay checksum mismatch')
    files, directories = inspect_tree(HERE / 'overlay')
    if manifest['files'] != files or manifest['directories'] != directories:
        raise ValueError('Saved overlay manifest does not match its complete source tree')
    command = [sys.executable, str(SOURCE / 'emmc/make-image.py'), args.mode,
               str(args.sd_release_gz), str(args.output_img)]
    if args.mode == 'installer':
        if not args.payload or not args.payload_manifest:
            parser.error('Installer requires --payload and --payload-manifest')
        payload = json.loads(args.payload_manifest.read_text())
        if payload['image']['name'] != NAMES['emmc'] or args.payload.name != NAMES['emmc'] + '.gz':
            raise ValueError('Installer must embed the test2 eMMC image')
        payload_sidecar = args.payload.with_suffix('').with_suffix('.manifest.json')
        if payload_sidecar.is_symlink() or not payload_sidecar.is_file():
            raise ValueError('The test2 eMMC build sidecar is required')
        built = json.loads(payload_sidecar.read_text())
        if (built.get('release') != 'test2-select-hotkey' or built.get('mode') != 'emmc'
                or built.get('board') != 'firefly-rk3399' or built.get('hotkey') != 'select'
                or built.get('image') != NAMES['emmc']
                or built.get('sha256') != payload['image']['sha256']
                or built.get('bytes') != payload['image']['bytes']
                or built.get('hotkey_overlay') != manifest['image']
                or built.get('hotkey_overlay_manifest_sha256') != digest(manifest_path)):
            raise ValueError('Payload build does not match the Select hotkey release')
        command += ['--payload', str(args.payload), '--payload-manifest', str(args.payload_manifest)]
    subprocess.run(command, check=True)
    drive = f'{args.output_img}@@16777216'
    for path, destination in [(overlay, 'boot/overlay'),
                              (HERE / 'docs/Select热键.md', 'SELECT-HOTKEY.txt'),
                              (HERE / 'docs/eMMC安装说明.md', 'FIREFLY-README.txt')]:
        subprocess.run(['mcopy', '-o', '-i', drive, str(path), '::/' + destination], check=True)
    subprocess.run([sys.executable, str(SOURCE / 'zero-free-fat.py'), str(args.output_img)], check=True)
    sidecar = args.output_img.with_suffix('.manifest.json')
    report = json.loads(sidecar.read_text())
    report.update({'sha256': digest(args.output_img), 'release': 'test2-select-hotkey',
                   'hotkey_overlay': manifest['image'],
                   'hotkey_overlay_manifest_sha256': digest(manifest_path),
                   'hotkey': 'select', 'hotkey_guide_sha256': digest(HERE / 'docs/Select热键.md'),
                   'install_guide_sha256': digest(HERE / 'docs/eMMC安装说明.md')})
    sidecar.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
