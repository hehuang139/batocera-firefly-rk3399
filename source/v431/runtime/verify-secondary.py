#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Validate actual 43.1 second-layer cores across its two-layer overlay."""
import argparse
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('runtime_helpers', HERE / 'verify-runtime.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
checks = []
SECONDARY_SHA256 = 'a2eb67cd4839d0f129a5aec0b4fe7c3df2d6c0208a40466c775ecea335e22197'


def check(name, passed, detail):
    checks.append({'name': name, 'pass': bool(passed), 'detail': detail})
    if not passed:
        raise ValueError(name + ': ' + str(detail))


class Overlay:
    """Primary files win; secondary directory contents remain visible."""
    def __init__(self, primary, secondary):
        self.layers = [('primary', primary), ('secondary', secondary)]
        self.nodes = {}

    def resolve(self, virtual):
        parts = list(PurePosixPath('/' + str(virtual).lstrip('/')).parts[1:])
        result, traversals, selected = [], 0, None
        while parts:
            item = parts.pop(0)
            if item in ('', '.'):
                continue
            if item == '..':
                if not result:
                    raise ValueError('Path escaped overlay: ' + str(virtual))
                result.pop()
                continue
            selected = next(((name, root.joinpath(*result, item)) for name, root in self.layers
                             if os.path.lexists(root.joinpath(*result, item))), None)
            if selected is None:
                return None
            if selected[1].is_symlink():
                traversals += 1
                if traversals > 40:
                    raise ValueError('Overlay symlink loop: ' + str(virtual))
                target = PurePosixPath(os.readlink(selected[1]))
                if target.is_absolute():
                    result = []
                parts = list(target.parts[1:] if target.is_absolute() else target.parts) + parts
            else:
                result.append(item)
        if selected is None:
            return None
        return '/' + '/'.join(result), selected[0], selected[1]

    def closure(self, start):
        todo, visited = [start], set()
        while todo:
            resolved = self.resolve(todo.pop())
            if resolved is None or not resolved[2].is_file():
                raise ValueError('Missing overlay ELF: ' + start)
            virtual, layer, path = resolved
            if virtual in visited:
                continue
            visited.add(virtual)
            if virtual not in self.nodes:
                info = helpers.elf_info(path)
                if info['machine'] != 183:
                    raise ValueError('Non-AArch64 ELF: ' + virtual)
                info.update({'layer': layer, 'bytes': path.stat().st_size,
                             'sha256': helpers.digest(path), 'resolved_needed': {}})
                origin = str(PurePosixPath(virtual).parent)
                search = []
                for entry in info['search']:
                    search.extend(part.replace('${ORIGIN}', origin).replace('$ORIGIN', origin)
                                  for part in entry.split(':') if part)
                search.extend(['/lib', '/lib64', '/usr/lib', '/usr/lib64',
                               '/usr/lib/aarch64-linux-gnu', '/lib/aarch64-linux-gnu'])
                conf = self.resolve('/etc/ld.so.conf')
                if conf:
                    search.extend(line.strip() for line in conf[2].read_text().splitlines()
                                  if line.strip().startswith('/'))
                for needed in info['needed']:
                    candidates = [needed] if '/' in needed else [item + '/' + needed for item in search]
                    found = next((value for value in (self.resolve(item) for item in candidates)
                                  if value and value[2].is_file()), None)
                    if found is None:
                        raise ValueError(f'Missing {needed} required by {virtual}')
                    info['resolved_needed'][needed] = found[0]
                self.nodes[virtual] = info
            info = self.nodes[virtual]
            todo.extend(info['resolved_needed'].values())
            if info['interpreter']:
                todo.append(info['interpreter'])
        return sorted(visited)


def main(args):
    root, secondary = args.rootfs.resolve(), args.secondary_rootfs.resolve()
    sqfs = args.secondary_squashfs.resolve()
    version = (root / 'usr/share/batocera/batocera.version').read_text().strip()
    check('actual-primary-is-43.1', bool(re.match(r'^43\.1(?:\D|$)', version)), version)
    check('original-43.1-secondary-bytes', sqfs.stat().st_size == 367181824, sqfs.stat().st_size)
    sha = helpers.digest(sqfs)
    check('original-43.1-secondary-sha256', sha == SECONDARY_SHA256, sha)
    cores = sorted((secondary / 'usr/lib/libretro').glob('*_libretro.so'))
    check('secondary-contains-103-libretro-cores', len(cores) == 103, len(cores))
    overlay = Overlay(root, secondary)
    closures = {}
    for path in cores:
        virtual = '/' + path.relative_to(secondary).as_posix()
        found = overlay.resolve(virtual)
        check('secondary-core-visible:' + path.name, found is not None and found[1] == 'secondary', virtual)
        closure = overlay.closure(virtual)
        closures[virtual] = closure
        check('aarch64-overlay-closure:' + path.name, bool(closure), {'files': len(closure)})
    qemu = shutil.which('qemu-aarch64-static')
    check('qemu-aarch64-available', bool(qemu), qemu)
    executed = []
    names = ['fceumm', 'gambatte', 'genesisplusgx', 'mgba', 'snes9x', 'snes9x_next']
    with tempfile.TemporaryDirectory(prefix='rk3399-v431-cores-') as temporary:
        env = {'PATH': '/usr/bin:/bin', 'HOME': temporary,
               'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1',
               'PYTHONHOME': str(root / 'usr')}
        for name in names:
            path = secondary / ('usr/lib/libretro/' + name + '_libretro.so')
            command = [qemu, '-cpu', 'cortex-a72', '-L', str(root),
                       str(helpers.resolve(root, '/usr/bin/python3')),
                       str(HERE / 'core-probe.py'), str(path)]
            result = subprocess.run(command, env=env, text=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, timeout=60)
            probe = {'core': name, 'cpu': 'cortex-a72', 'exit_code': result.returncode,
                     'output': result.stdout[-20000:]}
            match = re.search(r'^LIBRETRO_PROBE=(.+)$', result.stdout, re.M)
            if match:
                probe['libretro'] = json.loads(match[1])
            executed.append(probe)
            check('cortex-a72-core-init-deinit:' + name, result.returncode == 0 and
                  probe.get('libretro', {}).get('api') == 1 and
                  probe.get('libretro', {}).get('init_deinit') == 'PASS', probe)
    return {'version': version, 'secondary': {'bytes': sqfs.stat().st_size, 'sha256': sha,
            'core_count': len(cores)}, 'lowerdir_precedence': ['primary', 'secondary'],
            'closures': closures, 'elf_objects': overlay.nodes, 'executed': executed,
            'scope': 'All secondary libretro ELF64 AArch64 dependency closures across both official layers; six cores executed through libretro API version, system info, init and deinit using Cortex-A72 QEMU. No game ROMs or GPU rendering used.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rootfs', required=True, type=Path)
    parser.add_argument('--secondary-rootfs', required=True, type=Path)
    parser.add_argument('--secondary-squashfs', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    result = {}
    try:
        result.update(main(args))
    except Exception as error:
        result['error'] = f'{type(error).__name__}: {error}'
    result.update({'result': 'FAIL' if 'error' in result else 'PASS', 'checks': checks,
                   'passed': sum(item['pass'] for item in checks), 'total': len(checks)})
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ['result', 'passed', 'total']}, indent=2))
    if 'error' in result:
        print(result['error'])
        raise SystemExit(1)
