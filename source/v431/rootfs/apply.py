#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Apply the pinned Firefly delta to the genuine Batocera 43.1 rootfs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat

HERE = Path(__file__).resolve().parent


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8388608), b''):
            h.update(chunk)
    return h.hexdigest()


def target(root, relative):
    rel = Path(relative)
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError('Invalid root-relative path: ' + relative)
    path = root / rel
    if not path.parent.resolve().is_relative_to(root):
        raise ValueError('Parent escapes rootfs: ' + relative)
    return path


def identity(path):
    if path.is_symlink():
        return {'type': 'symlink', 'target': os.readlink(path)}
    if not path.exists():
        return None
    mode = path.lstat().st_mode
    if stat.S_ISREG(mode):
        return {'type': 'file', 'bytes': path.stat().st_size,
                'sha256': digest(path), 'mode': f'{stat.S_IMODE(mode):04o}'}
    if stat.S_ISDIR(mode):
        return {'type': 'directory', 'mode': f'{stat.S_IMODE(mode):04o}'}
    raise ValueError('Special input not allowed: ' + str(path))


def inventory(root, relative):
    base = target(root, relative)
    if base.is_symlink() or not base.is_dir():
        raise ValueError('Expected an ordinary directory: ' + str(base))
    return [{'path': p.relative_to(root).as_posix(), **identity(p)}
            for p in sorted(base.rglob('*'))]


def plan(root, bsp):
    manifest = json.loads((HERE / 'provenance.json').read_text())
    if (root == Path('/') or root == bsp or root.is_relative_to(bsp)
            or bsp.is_relative_to(root) or not (root / 'usr/share/batocera').is_dir()):
        raise ValueError('Expected separate extracted target and BSP rootfs trees')
    if (root / 'usr/share/batocera/batocera.version').read_text() != manifest['version_text']:
        raise ValueError('Expected the genuine pinned Batocera 43.1 release')
    for item in manifest['invariants']:
        if identity(target(root, item['path'])) != item['identity']:
            raise ValueError('Retained 43.1 file checksum mismatch: ' + item['path'])
    changes = []
    for item in manifest['files']:
        path = target(root, item['path'])
        current = identity(path)
        after = item['after']
        if current not in (item['before'], after):
            raise ValueError('Unexpected input: ' + item['path'])
        if item.get('source'):
            source = target(bsp, item['source'])
            if identity(source) != after:
                raise ValueError('BSP checksum mismatch: ' + item['source'])
        elif after:
            source = HERE / 'overlay' / item['path']
            if identity(source) != after:
                raise ValueError('Overlay checksum mismatch: ' + item['path'])
        else:
            source = None
        changes.append((item, path, source))
    modules = inventory(root, 'lib/modules')
    if modules not in (manifest['donor_modules'], manifest['bsp_modules']):
        raise ValueError('Unexpected target kernel module tree')
    if inventory(bsp, 'lib/modules') != manifest['bsp_modules']:
        raise ValueError('Pinned RK3399 module tree checksum mismatch')
    return manifest, changes


def write_file(path, source, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()
    shutil.copyfile(source, path)
    path.chmod(int(mode, 8))
    if os.geteuid() == 0:
        os.chown(path, 0, 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rootfs', type=Path, required=True)
    parser.add_argument('--bsp-rootfs', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    root, bsp = args.rootfs.resolve(), args.bsp_rootfs.resolve()
    manifest, changes = plan(root, bsp)
    if not args.check:
        # All inputs and sources are validated before the first mutation.
        for item, path, source in changes:
            if item['after'] is None:
                if path.exists() or path.is_symlink():
                    path.unlink()
            else:
                write_file(path, source, item['after']['mode'])
        modules = target(root, 'lib/modules')
        shutil.rmtree(modules)
        shutil.copytree(target(bsp, 'lib/modules'), modules, symlinks=True)
        if os.geteuid() == 0:
            for path in [modules, *modules.rglob('*')]:
                os.chown(path, 0, 0, follow_symlinks=False)
        if inventory(root, 'lib/modules') != manifest['bsp_modules']:
            raise ValueError('Copied module tree differs from pinned BSP')
    report = {'result': 'PASS', 'check_only': args.check, 'rootfs': str(root),
              'version_preserved': manifest['version_text'].strip(),
              'files': [item for item, _, _ in changes],
              'module_files': sum(item['type'] == 'file' for item in manifest['bsp_modules']),
              'removed_module_files': sum(item['type'] == 'file' for item in manifest['donor_modules']),
              'module_manifest_sha256': hashlib.sha256(json.dumps(manifest['bsp_modules'], sort_keys=True).encode()).hexdigest()}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'result': 'PASS', 'check_only': args.check,
                      'files': len(changes), 'module_files': report['module_files']}, indent=2))


if __name__ == '__main__':
    main()
