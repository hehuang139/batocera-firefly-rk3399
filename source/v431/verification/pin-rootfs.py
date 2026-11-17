#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Pin independent component and complete module checks from the frozen port."""
import argparse
import hashlib
import json
from pathlib import Path
import stat

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8388608), b''):
            value.update(chunk)
    return value.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rootfs', type=Path, required=True)
    p.add_argument('--base-content', type=Path, default=ROOT / 'work/v431/base-content.json')
    p.add_argument('--port-manifest', type=Path, default=ROOT / 'source/v431/rootfs/provenance.json')
    p.add_argument('--output', type=Path, default=HERE / 'rootfs-inputs.json')
    args = p.parse_args()
    base = json.loads(args.base_content.read_text())['files']
    port = json.loads(args.port_manifest.read_text())
    root = args.rootfs
    files = {}
    roles = {'usr/bin/emulationstation': 'emulationstation', 'usr/bin/retroarch': 'retroarch',
             'usr/bin/firefly-select-hotkey': 'select-script', 'etc/init.d/S30selecthotkey': 'select-init',
             'usr/bin/batocera-upgrade': 'upgrade-guard'}
    unchanged = ['usr/bin/emulationstation', 'usr/bin/retroarch', 'usr/bin/python3.12',
                 'lib/libc.so.6', 'lib/ld-linux-aarch64.so.1',
                 'usr/share/batocera/batocera.version',
                 'usr/lib/python3.12/site-packages/configgen/controllersConfig.py',
                 'usr/lib/python3.12/site-packages/configgen/generators/libretro/libretroControllers.py']
    gallium = sorted((root / 'usr/lib').glob('libgallium-*.so'))
    if len(gallium) != 1:
        raise ValueError('Expected one unchanged Mesa Gallium library')
    gallium_name = gallium[0].relative_to(root).as_posix()
    roles[gallium_name] = 'panfrost'
    unchanged.append(gallium_name)
    for name in unchanged:
        path = root / name
        expected = base[name]
        actual = digest(path)
        if actual != expected['sha256'] or path.stat().st_size != expected['bytes']:
            raise ValueError('Genuine 43.1 core component changed: ' + name)
        files[name] = {'path': name, 'bytes': path.stat().st_size, 'sha256': actual,
                       'upstream_sha256': expected['sha256'], 'role': roles.get(name, 'preserved-core'),
                       'elf': path.read_bytes()[:4] == b'\x7fELF'}
        if name == gallium_name:
            files[name]['contains'] = ['panfrost', 'MIDGARD_MESA_DEBUG', 'Mali-T860']
    absent = []
    for item in port['files']:
        name = item['path']
        after = item['after']
        if after is None:
            if (root / name).exists() or (root / name).is_symlink():
                raise ValueError('Removed donor path remains: ' + name)
            absent.append(name)
        else:
            if after['type'] != 'file':
                raise ValueError('Expected ordinary changed file: ' + name)
            path = root / name
            actual = digest(path)
            if actual != after['sha256'] or path.stat().st_size != after['bytes']:
                raise ValueError('Applied rootfs does not match port manifest: ' + name)
            files[name] = {'path': name, 'bytes': after['bytes'], 'sha256': actual,
                           'role': roles.get(name, 'board-adaptation'), 'elf': False}
    modules = port['bsp_modules']
    if not modules:
        raise ValueError('Missing complete kernel module manifest')
    result = {'version_path': 'usr/share/batocera/batocera.version',
              'arch_path': 'usr/share/batocera/batocera.arch', 'kernel_release': '6.6.27',
              'select_config_path': 'usr/share/emulationstation/es_input.cfg',
              'files': [files[name] for name in sorted(files)], 'modules': modules,
              'absent_paths': absent, 'port_manifest_sha256': digest(args.port_manifest),
              'base_content_sha256': digest(args.base_content)}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'files': len(files), 'module_entries': len(modules), 'absent_paths': len(absent),
                      'output': str(args.output)}, indent=2))


if __name__ == '__main__':
    main()
