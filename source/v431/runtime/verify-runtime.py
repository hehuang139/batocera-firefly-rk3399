#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Inspect ARM64 dependencies and run selected 43.1 programs as Cortex-A72.

Run inside the v431 builder with qemu-user-static. The rootfs stays read-only;
the report and temporary runtime home are the only writes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
checks = []


def check(name, passed, detail):
    checks.append({'name': name, 'pass': bool(passed), 'detail': detail})
    if not passed:
        raise ValueError(name + ': ' + str(detail))


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8388608), b''):
            value.update(block)
    return value.hexdigest()


def resolve(root, virtual):
    """Resolve absolute target symlinks inside root, rather than host /usr."""
    parts = list(PurePosixPath('/' + str(virtual).lstrip('/')).parts[1:])
    result, traversals = [], 0
    while parts:
        item = parts.pop(0)
        if item in ('', '.'):
            continue
        if item == '..':
            if not result:
                raise ValueError('Target path escaped root: ' + str(virtual))
            result.pop()
            continue
        path = root.joinpath(*result, item)
        if path.is_symlink():
            traversals += 1
            if traversals > 40:
                raise ValueError('Target symlink loop: ' + str(virtual))
            target = PurePosixPath(os.readlink(path))
            if target.is_absolute():
                result = []
            parts = list(target.parts[1:] if target.is_absolute() else target.parts) + parts
        else:
            result.append(item)
    return root.joinpath(*result)


def elf_info(path):
    with path.open('rb') as stream:
        header = stream.read(64)
        if not header.startswith(b'\x7fELF'):
            raise ValueError('Not ELF: ' + str(path))
        if header[4:6] != b'\x02\x01':
            raise ValueError('Expected little-endian ELF64: ' + str(path))
        fields = struct.unpack('<16sHHIQQQIHHHHHH', header)
        machine, program_offset, program_size, program_count = fields[2], fields[5], fields[9], fields[10]
        segments, dynamic, interpreter = [], None, None
        for index in range(program_count):
            stream.seek(program_offset + index * program_size)
            value = struct.unpack('<IIQQQQQQ', stream.read(56))
            kind, offset, address, length = value[0], value[2], value[3], value[5]
            if kind == 1:
                segments.append((address, offset, length))
            elif kind == 2:
                dynamic = (offset, length)
            elif kind == 3:
                stream.seek(offset)
                interpreter = stream.read(length).rstrip(b'\x00').decode()
        needed, paths, strtab, size = [], [], None, None
        if dynamic:
            stream.seek(dynamic[0])
            entries = []
            for _ in range(dynamic[1] // 16):
                tag, value = struct.unpack('<qQ', stream.read(16))
                if tag == 0:
                    break
                entries.append((tag, value))
                if tag == 5:
                    strtab = value
                elif tag == 10:
                    size = value
            if strtab is not None:
                match = next((segment for segment in segments
                              if segment[0] <= strtab < segment[0] + segment[2]), None)
                if match is None or size is None:
                    raise ValueError('Invalid ELF string table: ' + str(path))
                stream.seek(match[1] + strtab - match[0])
                strings = stream.read(size)
                for tag, offset in entries:
                    if tag in (1, 15, 29):
                        value = strings[offset:].split(b'\x00', 1)[0].decode()
                        (needed if tag == 1 else paths).append(value)
        return {'machine': machine, 'interpreter': interpreter, 'needed': needed, 'search': paths}


def dependency_closure(root, start):
    cache, todo = {}, [resolve(root, start)]
    directories = ['/lib', '/lib64', '/usr/lib', '/usr/lib64', '/usr/lib/aarch64-linux-gnu', '/lib/aarch64-linux-gnu']
    conf = root / 'etc/ld.so.conf'
    if conf.is_file():
        for line in conf.read_text().splitlines():
            line = line.strip()
            if line.startswith('/'):
                directories.append(line)
    while todo:
        path = todo.pop()
        relative = '/' + path.relative_to(root).as_posix()
        if relative in cache:
            continue
        info = elf_info(path)
        if info['machine'] != 183:
            raise ValueError('Non-AArch64 dependency: ' + relative)
        info.update({'sha256': digest(path), 'bytes': path.stat().st_size})
        cache[relative] = info
        if info['interpreter']:
            todo.append(resolve(root, info['interpreter']))
        origin = str(PurePosixPath(relative).parent)
        search = []
        for entry in info['search']:
            search.extend(part.replace('${ORIGIN}', origin).replace('$ORIGIN', origin)
                          for part in entry.split(':') if part)
        info['resolved_needed'] = {}
        for needed in info['needed']:
            if '/' in needed:
                candidates = [resolve(root, needed)]
            else:
                candidates = [resolve(root, directory + '/' + needed) for directory in search + directories]
            selected = next((candidate for candidate in candidates if candidate.is_file()), None)
            if selected is None:
                raise ValueError(f'Missing dependency {needed} required by {relative}; paths={search + directories}')
            info['resolved_needed'][needed] = '/' + selected.relative_to(root).as_posix()
            todo.append(selected)
    return cache


def execute(qemu, root, target, arguments, environment, timeout=60):
    path = resolve(root, target)
    command = [str(qemu), '-cpu', 'cortex-a72', '-L', str(root), str(path), *arguments]
    result = subprocess.run(command, env=environment, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=timeout)
    return {'target': target, 'arguments': arguments, 'cpu': 'cortex-a72',
            'exit_code': result.returncode, 'output': result.stdout[-20000:]}


def main(args):
    root = args.rootfs.resolve()
    check('rootfs-directory', root != Path('/') and (root / 'usr/share/batocera').is_dir(), str(root))
    donor = (HERE / 'provenance/batocera-s922x.board').read_text()
    target = (HERE / 'provenance/batocera-rk3399.board').read_text()
    check('source-isa-common-armv8', all('BR2_aarch64=y' in source and
          'BR2_ARM_FPU_NEON_FP_ARMV8=y' in source for source in (donor, target)),
          {'donor': 'cortex_a73_a53', 'target': 'cortex_a72_a53', 'ISA': 'AArch64 ARMv8-A NEON'})
    check('source-common-panfrost-wayland', all('BR2_PACKAGE_BATOCERA_PANFROST_MESA3D=y' in source
          and 'BR2_PACKAGE_BATOCERA_WAYLAND_LABWC=y' in source for source in (donor, target)),
          'Both exact 43.1 board definitions select Mesa Panfrost and Wayland/Labwc')
    # Keep this tied to the actual retained RK3399 kernel configuration.
    kernel_config = HERE.parents[1] / 'kernel/base-kernel.config'
    config_lines = set(kernel_config.read_text().splitlines())
    required_config = ['DMA_SHARED_BUFFER', 'INPUT_UINPUT', 'UNIX', 'POSIX_TIMERS',
                       'SECCOMP', 'SECCOMP_FILTER', 'EPOLL', 'EXT4_FS', 'SQUASHFS',
                       'OVERLAY_FS', 'DRM_PANFROST', 'DRM_ROCKCHIP', 'SYNC_FILE',
                       'EVENTFD', 'FUTEX', 'INOTIFY_USER', 'MEMFD_CREATE',
                       'DEVTMPFS', 'INPUT_EVDEV', 'BT', 'BT_HCIUART', 'BT_HCIUART_BCM',
                       'DRM_DW_HDMI', 'DRM_DW_HDMI_AHB_AUDIO']
    check('retained-kernel-userspace-features', all('CONFIG_' + key + '=y' in config_lines
          for key in required_config), required_config)
    check('retained-kernel-wireless-modules', all('CONFIG_' + key + '=m' in config_lines
          for key in ['BRCMFMAC', 'BT_HCIBTUSB']), ['BRCMFMAC=m', 'BT_HCIBTUSB=m'])
    mesa_source = (HERE / 'provenance/panfrost_kmod.c').read_text()
    kernel_source = (HERE / 'provenance/linux66-panfrost_drv.c').read_text()
    check('panfrost-drm-version-backward-compatibility',
          'version->version_minor < 1' in mesa_source and
          re.search(r'\.major\s*= 1,', kernel_source) is not None and
          re.search(r'\.minor\s*= 2,', kernel_source) is not None,
          {'Mesa 25.3.6 minimum DRM interface': '1.1', 'Linux 6.6 interface': '1.2'})
    check('panfrost-syncobj-and-optional-ioctls', 'DRIVER_SYNCOBJ' in kernel_source
          and 'dev->driver.version.minor >= 3' in mesa_source
          and 'dev->driver.version.minor >= 4' in mesa_source,
          'Syncobj is a DRM driver feature, not a separate CONFIG_DRM_SYNCOBJ option; newer timestamp and label calls are guarded')
    version_path = root / 'usr/share/batocera/batocera.version'
    version = version_path.read_text().strip()
    check('actual-rootfs-version', re.match(r'^43\.1(?:\D|$)', version) is not None, version)
    runtime_files = ['usr/bin/python3', 'usr/bin/retroarch', 'usr/bin/emulationstation',
                     'usr/bin/labwc', 'usr/lib/libEGL.so.1', 'usr/lib/libGLESv2.so.2']
    gallium = sorted((root / 'usr/lib').glob('libgallium-*.so'))
    check('mesa-gallium-library', len(gallium) == 1, [path.name for path in gallium])
    runtime_files.append(gallium[0].relative_to(root).as_posix())
    gallium_bytes = gallium[0].read_bytes()
    check('mesa-panfrost-midgard-t860', all(value in gallium_bytes for value in
          [b'panfrost\x00', b'MIDGARD_MESA_DEBUG\x00', b'Mali-T860\x00']),
          'Unified Mesa Gallium library contains Panfrost, Midgard and Mali-T860 support')
    closures = {}
    for relative in runtime_files:
        path = resolve(root, relative)
        check('runtime-file:' + relative, path.is_file(), str(path))
        closure = dependency_closure(root, relative)
        closures[relative] = closure
        check('aarch64-dependency-closure:' + relative, bool(closure),
              {'files': len(closure), 'sha256': closure['/' + path.relative_to(root).as_posix()]['sha256']})
    qemu = Path(shutil.which('qemu-aarch64-static') or '')
    check('qemu-aarch64-available', qemu.is_file(), str(qemu))
    executed = []
    with tempfile.TemporaryDirectory(prefix='rk3399-v431-runtime-') as temporary:
        environment = {'PATH': '/usr/bin:/bin', 'HOME': temporary, 'XDG_CONFIG_HOME': temporary,
                       'XDG_CACHE_HOME': temporary, 'XDG_RUNTIME_DIR': temporary,
                       'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1',
                       'PYTHONHOME': str(root / 'usr'), 'SDL_VIDEODRIVER': 'dummy',
                       'LIBGL_ALWAYS_SOFTWARE': '1'}
        probe = execute(qemu, root, '/usr/bin/python3', ['-c',
            'import sys,ssl,ctypes,hashlib,xml.etree.ElementTree,json; '
            'print(json.dumps({"python":sys.version,"openssl":ssl.OPENSSL_VERSION,"sha256":hashlib.sha256(b"Firefly").hexdigest()}))'], environment)
        executed.append(probe)
        check('cortex-a72-python-standard-library', probe['exit_code'] == 0 and '3.12.' in probe['output'], probe)
        for program, expression in [('retroarch', 'RetroArch'), ('emulationstation', 'EmulationStation'), ('labwc', 'labwc')]:
            # This exact ES revision exposes its version through --help;
            # --version is ignored and instead starts the graphical frontend.
            arguments = ['--help'] if program == 'emulationstation' else ['--version']
            probe = execute(qemu, root, '/usr/bin/' + program, arguments, environment)
            executed.append(probe)
            check('cortex-a72-version:' + program, probe['exit_code'] == 0 and expression.lower() in probe['output'].lower(), probe)
        package = next(iter(sorted((root / 'usr/lib').glob('python3.*/site-packages/configgen'))), None)
        check('configgen-package-present', package is not None, str(package))
        env = dict(environment)
        env['PYTHONPATH'] = str(package.parent)
        probe = execute(qemu, root, '/usr/bin/python3', ['-c',
            'import configgen.controllersConfig,configgen.Emulator,configgen.generators.libretro.libretroGenerator; print("configgen imports PASS")'], env)
        executed.append(probe)
        check('cortex-a72-configgen-imports', probe['exit_code'] == 0 and 'PASS' in probe['output'], probe)
    module_dir = root / 'lib/modules'
    releases = sorted(path.name for path in module_dir.iterdir() if path.is_dir())
    check('kernel-module-release-only-rk3399', releases == ['6.6.27'], releases)
    panfrost = list((module_dir / '6.6.27').rglob('panfrost.ko*'))
    builtins = (module_dir / '6.6.27/modules.builtin').read_text().splitlines()
    check('panfrost-built-into-retained-kernel', not panfrost and
          'kernel/drivers/gpu/drm/panfrost/panfrost.ko' in builtins
          and 'CONFIG_DRM_PANFROST=y' in config_lines,
          'Panfrost is built into the matched RK3399 kernel; modules.builtin and actual kernel configuration agree')
    wireless = list((module_dir / '6.6.27').rglob('brcmfmac.ko*'))
    check('brcmfmac-matching-module-present', len(wireless) == 1,
          [str(path.relative_to(root)) for path in wireless])
    module_info = subprocess.check_output(['modinfo', str(wireless[0])], text=True)
    check('brcmfmac-kernel-module-vermagic', re.search(r'^vermagic:\s+6\.6\.27\s', module_info, re.M) is not None, module_info)
    return {'version': version, 'rootfs': str(root), 'closures': closures, 'executed': executed,
            'kernel_modules': releases, 'scope': 'AArch64 ELF dependency closure and selected Cortex-A72 user-mode execution; kernel module metadata and exact 43.1 build configurations inspected.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rootfs', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = {}
    try:
        result.update(main(args))
    except Exception as error:
        result['error'] = f'{type(error).__name__}: {error}'
    result.update({'result': 'FAIL' if 'error' in result else 'PASS', 'checks': checks,
                   'passed': sum(item['pass'] for item in checks), 'total': len(checks)})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ['result', 'passed', 'total']}, indent=2))
    if 'error' in result:
        print(result['error'])
        raise SystemExit(1)
