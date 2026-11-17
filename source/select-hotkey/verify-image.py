#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read-only test2 image validation, extending the frozen eMMC verifier.

The baseline verifier is imported without modification. Its only adaptations
are the two exact embedded payload names, which are strictly checked as test2.
No baseline failure is suppressed. Run with the same builder as test1.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BASELINE_SHA256 = '7a393d7fadb7a7aff41c47e6563173b0686ee5a44b26227195e5576f9c63a4ac'
INIT_SHA256 = '48c3090a2809b009ca7752d3326369c6a6eb31a3574d2d0507d83afbc57b5dc8'
PAYLOAD_RAW = 'batocera40-firefly-rk3399-emmc-test2.img'
PAYLOAD_GZIP = PAYLOAD_RAW + '.gz'
INSTALLER_RAW = 'batocera40-firefly-rk3399-emmc-installer-tf-test2.img'
FAT_OFFSET = 16777216
OVERLAY_BYTES = 16 * 1024 * 1024
EXPECTED_FILES = {
    'usr/share/batocera/datainit/system/configs/emulationstation/es_input.cfg': 0o644,
    'usr/bin/firefly-select-hotkey': 0o755,
    'etc/init.d/S30selecthotkey': 0o755,
}
checks = []


def check(name, ok, detail):
    checks.append({'name': name, 'pass': bool(ok), 'detail': detail})
    if not ok:
        raise RuntimeError(f'{name}: {detail}')


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8388608), b''):
            value.update(chunk)
    return value.hexdigest()


def run(arguments):
    return subprocess.check_output(arguments, text=True, stderr=subprocess.STDOUT).strip()


def relative_path(value, allow_root=False):
    if not isinstance(value, str):
        raise ValueError('Overlay path must be text')
    if allow_root and value in ('/', '.'):
        return ''
    path = PurePosixPath(value.lstrip('/'))
    if (not re.fullmatch(r'[A-Za-z0-9_./-]+', value) or '..' in path.parts
            or not path.parts or path.parts[0].startswith('.')
            or str(path) != value.lstrip('/')):
        raise ValueError(f'Invalid overlay path: {value}')
    return str(path)


def permission_mode(value):
    if isinstance(value, str):
        return int(value, 8)
    if isinstance(value, int):
        return value
    raise ValueError(f'Invalid permission mode: {value!r}')


def debugfs(image, command):
    return run(['debugfs', '-R', command, str(image)])


def debugfs_quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'


def enumerate_overlay(image):
    """List every reachable inode without mounting or following symlinks."""
    entries = {}
    visited_directories = set()

    def visit(path):
        output = debugfs(image, 'ls -l -p /' + path)
        lines = [line for line in output.splitlines() if line.startswith('/')]
        if not lines:
            raise ValueError(f'Cannot enumerate overlay directory: /{path}')
        for line in lines:
            fields = line.split('/')
            if len(fields) != 8:
                raise ValueError(f'Unexpected debugfs directory entry: {line}')
            _, inode, mode, uid, gid, name, size, _ = fields
            if name == '..':
                continue
            if name == '.':
                key = path
            else:
                key = relative_path(path + '/' + name if path else name)
            metadata = {'inode': int(inode), 'mode': int(mode, 8),
                        'uid': int(uid), 'gid': int(gid),
                        'bytes': None if not size else int(size)}
            if name == '.':
                if path not in entries:
                    entries[path] = metadata
                elif entries[path] != metadata:
                    raise ValueError(f'Inconsistent directory inode: /{path}')
                continue
            if key in entries:
                raise ValueError(f'Duplicate overlay path: /{key}')
            entries[key] = metadata
            if stat.S_ISDIR(metadata['mode']):
                if metadata['inode'] in visited_directories:
                    raise ValueError(f'Directory cycle in overlay: /{key}')
                visited_directories.add(metadata['inode'])
                visit(key)

    visited_directories.add(2)
    visit('')
    return entries


def verify_overlay(image, manifest, source_asset, scratch):
    """Validate the saved filesystem itself, independently of FAT/container."""
    actual_hash = digest(image)
    declared_image = manifest['image']
    check('overlay-image-bytes', image.stat().st_size == declared_image['bytes'] == OVERLAY_BYTES,
          image.stat().st_size)
    check('overlay-image-hash', actual_hash == declared_image['sha256'] == digest(source_asset), actual_hash)
    with image.open('rb') as stream:
        stream.seek(1024)
        sb = stream.read(1024)
    check('overlay-ext4-magic', sb[56:58] == b'\x53\xef', sb[56:58].hex())
    state = struct.unpack_from('<H', sb, 58)[0]
    compatible = struct.unpack_from('<I', sb, 92)[0]
    incompatible = struct.unpack_from('<I', sb, 96)[0]
    check('overlay-clean-no-journal', state == 1 and not compatible & 4 and not incompatible & 4,
          {'state': state, 'has_journal': bool(compatible & 4), 'needs_recovery': bool(incompatible & 4)})
    fsck = subprocess.run(['e2fsck', '-f', '-n', str(image)], text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    check('overlay-e2fsck-readonly', fsck.returncode == 0, fsck.stdout.strip())
    check('overlay-unmodified-by-inspection', digest(image) == actual_hash, actual_hash)

    files, directories = {}, {}
    for item in manifest['files']:
        path = relative_path(item['path'])
        if path in files:
            raise ValueError(f'Duplicate file in overlay manifest: {path}')
        files[path] = item
    for item in manifest['directories']:
        path = relative_path(item['path'], allow_root=True)
        if path in directories:
            raise ValueError(f'Duplicate directory in overlay manifest: {path}')
        directories[path] = item
    check('overlay-exact-three-replacements', set(files) == set(EXPECTED_FILES), sorted(files))
    needed_directories = {''}
    for path in files:
        needed_directories.update(str(parent) if str(parent) != '.' else ''
                                  for parent in PurePosixPath(path).parents)
    # The ext4 root is always checked, whether or not explicitly listed.
    directories.setdefault('', {'path': '/', 'mode': '0755'})
    check('overlay-manifest-directories', set(directories) == needed_directories, sorted(directories))
    entries = enumerate_overlay(image)
    check('overlay-no-extra-paths', set(entries) == set(files) | needed_directories, sorted(entries))
    total_bytes = 0
    for path, item in sorted(entries.items()):
        kind = stat.S_IFMT(item['mode'])
        required = stat.S_IFREG if path in files else stat.S_IFDIR
        expected_mode = EXPECTED_FILES[path] if path in files else 0o755
        declared_mode = permission_mode((files if path in files else directories)[path]['mode'])
        check('overlay-inode:/' + path,
              kind == required and stat.S_IMODE(item['mode']) == declared_mode == expected_mode
              and item['uid'] == item['gid'] == 0,
              {**item, 'mode': oct(item['mode']), 'expected_mode': oct(expected_mode)})
        if path not in files:
            continue
        destination = scratch / 'overlay-file-content' / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        debugfs(image, f'dump /{path} {debugfs_quote(destination)}')
        file_hash = digest(destination)
        file_bytes = destination.stat().st_size
        check('overlay-content:/' + path, file_bytes == files[path]['bytes'] == item['bytes']
              and file_hash == files[path]['sha256'], {'bytes': file_bytes, 'sha256': file_hash})
        total_bytes += file_bytes
    check('overlay-fits-initrd-tmpfs', total_bytes < 8 * 1024 * 1024,
          {'file_bytes': total_bytes, 'initrd_tmpfs_bytes': 256 * 1024 * 1024})
    return actual_hash


def verify_source_tree(manifest):
    source = HERE / 'overlay'
    declared = {relative_path(item['path']): item for item in manifest['files']}
    directories = {relative_path(item['path'], allow_root=True) for item in manifest['directories']}
    directories.add('')
    actual = {''}
    check('overlay-source-root-directory', source.is_dir() and not source.is_symlink(), str(source))
    for path in source.rglob('*'):
        relative = relative_path(path.relative_to(source).as_posix())
        metadata = path.lstat()
        actual.add(relative)
        if relative in declared:
            item = declared[relative]
            check('overlay-source-file:' + relative,
                  stat.S_ISREG(metadata.st_mode) and metadata.st_size == item['bytes']
                  and stat.S_IMODE(metadata.st_mode) == permission_mode(item['mode'])
                  and digest(path) == item['sha256'], item)
        else:
            check('overlay-source-directory:' + relative,
                  relative in directories and stat.S_ISDIR(metadata.st_mode), relative)
    check('overlay-source-exact-paths', actual == set(declared) | directories, sorted(actual))


def verify_initrd(initrd, scratch):
    cpio_data = subprocess.check_output(['lz4', '-dc', str(initrd)])
    result = subprocess.run(['cpio', '--extract', '--to-stdout', 'init'],
                            input=cpio_data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            cwd=scratch)
    check('actual-initrd-init-extraction', result.returncode == 0,
          result.stderr.decode(errors='replace').strip())
    init_hash = hashlib.sha256(result.stdout).hexdigest()
    check('actual-initrd-init-pinned', init_hash == INIT_SHA256, init_hash)
    text = result.stdout.decode('utf-8')
    operations = [
        'mount -t tmpfs -o size=256M tmpfs /overlay_root',
        'if test -f /boot_root/boot/overlay',
        'mount -o ro /boot_root/boot/overlay /overlay_root/saved',
        'cp -pr /overlay_root/saved/* /overlay_root/overlay',
        'mount -t overlay overlay',
        'exec switch_root /new_root /sbin/init',
    ]
    positions = [text.find(operation) for operation in operations]
    check('overlay-loaded-before-system-init', all(position >= 0 for position in positions)
          and positions == sorted(positions), operations)
    config = (ROOT / 'source/kernel/base-kernel.config').read_text().splitlines()
    required = ['CONFIG_EXT4_FS=y', 'CONFIG_BLK_DEV_LOOP=y', 'CONFIG_OVERLAY_FS=y']
    check('overlay-kernel-support-built-in', all(line in config for line in required), required)


def main(args):
    baseline_path = ROOT / 'source/emmc/verify-image.py'
    baseline_hash = digest(baseline_path)
    check('baseline-verifier-frozen', baseline_hash == BASELINE_SHA256, baseline_hash)
    spec = importlib.util.spec_from_file_location('firefly_frozen_emmc_verifier', baseline_path)
    baseline = importlib.util.module_from_spec(spec)
    # Keep the frozen source directory untouched, including bytecode caches.
    old_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(baseline)
    finally:
        sys.dont_write_bytecode = old_dont_write_bytecode
    adapted = []
    names = {'embedded-payload-filename': PAYLOAD_GZIP, 'embedded-raw-filename': PAYLOAD_RAW}

    def test2_check(name, ok, detail):
        if name in names:
            adapted.append(name)
            check(name, detail == names[name], {'actual': detail, 'expected': names[name]})
        else:
            check(name, ok, detail)

    baseline.check = test2_check
    baseline.checks = checks
    expected_image = PAYLOAD_RAW if args.mode == 'emmc' else INSTALLER_RAW
    check('test2-image-filename', args.image.name == expected_image, args.image.name)
    result = baseline.main(args)
    expected_adaptations = [] if args.mode == 'emmc' else list(names)
    check('baseline-name-adaptations-exact', adapted == expected_adaptations,
          {'adapted_checks': adapted, 'strict_expected_names': names,
           'all_other_checks': 'unchanged', 'baseline_sha256': baseline_hash})
    scratch = args.scratch or ROOT / 'work/select-hotkey/verify-image'
    scratch.mkdir(parents=True, exist_ok=True)
    manifest_path = HERE / 'assets/overlay-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    asset = HERE / 'assets/overlay'
    sidecar = json.loads(args.image.with_suffix('.manifest.json').read_text())
    check('test2-sidecar-release', sidecar.get('release') == 'test2-select-hotkey'
          and sidecar.get('hotkey') == 'select',
          {'release': sidecar.get('release'), 'hotkey': sidecar.get('hotkey')})
    check('test2-sidecar-overlay', sidecar.get('hotkey_overlay') == manifest['image']
          and manifest['image']['name'] == 'overlay', sidecar.get('hotkey_overlay'))
    check('test2-sidecar-overlay-manifest', sidecar.get('hotkey_overlay_manifest_sha256') == digest(manifest_path),
          digest(manifest_path))
    verify_source_tree(manifest)
    with tempfile.TemporaryDirectory(prefix='test2-extra-', dir=scratch) as directory:
        temporary = Path(directory)

        def extract(remote):
            target = temporary / relative_path(remote)
            target.parent.mkdir(parents=True, exist_ok=True)
            run(['mcopy', '-i', f'{args.image.resolve()}@@{FAT_OFFSET}', '::/' + remote, str(target)])
            return target

        overlay = extract('boot/overlay')
        result['overlay_sha256'] = verify_overlay(overlay, manifest, asset, temporary)
        verify_initrd(extract('boot/initrd.lz4'), temporary)
        listing = run(['mdir', '-b', '-i', f'{args.image.resolve()}@@{FAT_OFFSET}', '::/boot'])
        check('no-pending-rootfs-update', not any(PurePosixPath(line.strip()).name == 'batocera.update'
              for line in listing.splitlines()), listing)
        for name, source, field in [
            ('FIREFLY-README.txt', HERE / 'docs/eMMC安装说明.md', 'install_guide_sha256'),
            ('SELECT-HOTKEY.txt', HERE / 'docs/Select热键.md', 'hotkey_guide_sha256'),
        ]:
            actual = digest(extract(name))
            check('test2-document:' + name, actual == digest(source) == sidecar.get(field), actual)
    result['overlay_manifest_sha256'] = digest(manifest_path)
    result['baseline_verifier_sha256'] = baseline_hash
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', required=True, choices=['emmc', 'installer'])
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--gzip', type=Path)
    parser.add_argument('--skip-gzip', action='store_true')
    parser.add_argument('--scratch', type=Path)
    parser.add_argument('--report', type=Path, required=True)
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
    print(f"test2 image verification: {result['passed']}/{result['total']} {result['result']}")
    if 'error' in result:
        print(result['error'])
        raise SystemExit(1)
