#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read-only verification of genuine Batocera 43.1 Firefly RK3399 images.

Runs in the pinned builder container. Reads ordinary image files only; never
mounts a filesystem or opens a block device. All large temporary files live in
--scratch and disappear on success or failure.
"""
import argparse
import ast
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SECTOR = 512
P1_START = 32768
SHARE_SECTORS = 524288
GEOMETRIES = {
    'emmc': {'bytes': 4580179968, 'fat_sectors': 8388608,
             'root': '/dev/mmcblk2p1', 'name': 'batocera431-firefly-rk3399-emmc-test1.img'},
    'installer': {'bytes': 6727663616, 'fat_sectors': 12582912,
                  'root': '/dev/mmcblk1p1', 'name': 'batocera431-firefly-rk3399-emmc-installer-tf-test1.img'},
}
SECONDARY = {'bytes': 367181824, 'sha256': 'a2eb67cd4839d0f129a5aec0b4fe7c3df2d6c0208a40466c775ecea335e22197'}
checks = []


def check(name, condition, detail):
    checks.append({'name': name, 'pass': bool(condition), 'detail': detail})
    if not condition:
        raise RuntimeError(f'{name}: {detail}')


def run(arguments, **kwargs):
    return subprocess.check_output(arguments, stderr=subprocess.STDOUT, **kwargs)


def text(arguments):
    return run(arguments).decode(errors='replace').strip()


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8388608), b''):
            value.update(chunk)
    return value.hexdigest()


def hash_gzip(path):
    value, length = hashlib.sha256(), 0
    with gzip.open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(8388608), b''):
            value.update(chunk)
            length += len(chunk)
    return value.hexdigest(), length


def ordinary(path):
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('Expected an ordinary file: ' + str(path))


def relative(value):
    if not isinstance(value, str):
        raise ValueError('Expected a relative path string')
    value = value.lstrip('/')
    path = PurePosixPath(value)
    if not value or '..' in path.parts or str(path) != value or path.is_absolute():
        raise ValueError('Invalid relative path: ' + value)
    return value


def pinned(path, metadata, name):
    ordinary(path)
    actual = {'bytes': path.stat().st_size, 'sha256': sha(path)}
    check(name, actual['bytes'] == metadata['bytes'] and actual['sha256'] == metadata['sha256'], actual)
    return actual


def read_at(stream, offset, length):
    stream.seek(offset)
    value = stream.read(length)
    if len(value) != length:
        raise ValueError(f'Short read at {offset}: {len(value)} != {length}')
    return value


def region_hash(stream, offset, length):
    stream.seek(offset)
    value = hashlib.sha256()
    while length:
        data = stream.read(min(length, 8388608))
        if not data:
            raise ValueError('Short region read')
        value.update(data)
        length -= len(data)
    return value.hexdigest()


def copy_region(stream, offset, length, target):
    stream.seek(offset)
    remaining = length
    with target.open('xb') as dst:
        while remaining:
            chunk = stream.read(min(8388608, remaining))
            if not chunk:
                raise ValueError('Short partition read')
            if any(chunk):
                dst.write(chunk)
            else:
                dst.seek(len(chunk), 1)
            remaining -= len(chunk)
        dst.truncate(length)


def dtprop(path, node, prop, kind='s'):
    return text(['fdtget', '-t', kind, str(path), node, prop])


def verify_mbr(stream, mode):
    geometry = GEOMETRIES[mode]
    mbr = read_at(stream, 0, SECTOR)
    check('mbr-signature', mbr[510:] == b'\x55\xaa', mbr[510:].hex())
    expected = [(12, P1_START, geometry['fat_sectors']),
                (131, P1_START + geometry['fat_sectors'], SHARE_SECTORS)]
    for number in range(4):
        row = mbr[446 + number * 16:462 + number * 16]
        if number < 2:
            actual = (row[4], *struct.unpack_from('<II', row, 8))
            check(f'partition-{number + 1}', actual == expected[number] and row[0] in (0, 0x80),
                  {'type_start_count': actual, 'boot_flag': row[0]})
        else:
            check(f'partition-{number + 1}-empty', row == bytes(16), row.hex())
    end = (expected[1][1] + expected[1][2]) * SECTOR
    check('partitions-cover-image-exactly', end == geometry['bytes'], end)
    return expected


def verify_boot(stream, mode, scratch):
    source = ROOT / ('source/emmc/boot' if mode == 'emmc' else 'source/boot')
    assets = ROOT / ('source/emmc/boot-assets' if mode == 'emmc' else 'source/boot-assets')
    manifest = json.loads((source / 'manifest.json').read_text())
    check('boot-build-validation', manifest.get('result') == 'PASS'
          and all(item['pass'] for item in manifest['checks']), source.relative_to(ROOT).as_posix())
    records = {item['name']: item for item in manifest['assets']}
    extents = [(0, SECTOR, 'MBR')]
    payloads = {}
    for name, offset in [('idbloader.img', 32768), ('u-boot.itb', 8388608)]:
        item = records[name]
        reference = assets / name
        pinned(reference, {'bytes': item['size'], 'sha256': item['sha256']}, 'boot-source:' + name)
        payload = read_at(stream, offset, item['size'])
        check('boot-image:' + name, hashlib.sha256(payload).hexdigest() == item['sha256'],
              {'offset': offset, 'bytes': len(payload), 'sha256': item['sha256']})
        payloads[name] = payload
        extents.append((offset, offset + len(payload), name))
    extents.append((P1_START * SECTOR, P1_START * SECTOR, 'FAT'))
    for previous, following in zip(extents, extents[1:]):
        check('boot-nonoverlap:' + previous[2], previous[1] <= following[0], [previous, following])
        gap = read_at(stream, previous[1], following[0] - previous[1])
        check('boot-zero-gap:' + previous[2], not any(gap), {'start': previous[1], 'bytes': len(gap)})
    fit = scratch / 'u-boot.itb'
    fit.write_bytes(payloads['u-boot.itb'])
    image_nodes = text(['fdtget', '-l', str(fit), '/images']).splitlines()
    check('fit-firefly-control-node', 'fdt-1' in image_nodes, image_nodes)
    control = scratch / 'control.dtb'
    text(['dumpimage', '-T', 'flat_dt', '-p', str(image_nodes.index('fdt-1')),
          '-o', str(control), str(fit)])
    control_meta = records['u-boot.dtb']
    pinned(control, {'bytes': control_meta['size'], 'sha256': control_meta['sha256']}, 'fit-control-dtb')
    check('fit-control-firefly-compatible', dtprop(control, '/', 'compatible') == 'firefly,firefly-rk3399 rockchip,rk3399',
          dtprop(control, '/', 'compatible'))
    check('fit-control-mmc-aliases', dtprop(control, '/aliases', 'mmc0') == '/mmc@fe330000'
          and dtprop(control, '/aliases', 'mmc1') == '/mmc@fe320000', 'U-Boot eMMC=mmc0, TF=mmc1')
    expected_target = b'boot_targets=mmc1 mmc0\0' if mode == 'emmc' else b'boot_targets=mmc1\0'
    check('fit-boot-targets', expected_target in payloads['u-boot.itb'], expected_target.decode().rstrip('\0'))
    built_config = (source / 'built.config').read_text().splitlines()
    check('boot-memory-only-environment', 'CONFIG_ENV_IS_NOWHERE=y' in built_config
          and '# CONFIG_ENV_IS_IN_MMC is not set' in built_config, 'No saved MMC environment')
    check('boot-linux-owns-display', '# CONFIG_VIDEO is not set' in built_config, 'U-Boot VIDEO disabled')


def verify_dtb(path, metadata):
    pinned(path, metadata, 'linux-dtb-hash')
    properties = [('/', 'model', 'Firefly-RK3399 Board', 's'),
                  ('/', 'compatible', 'firefly,firefly-rk3399 rockchip,rk3399', 's'),
                  ('/aliases', 'mmc1', '/mmc@fe320000', 's'),
                  ('/aliases', 'mmc2', '/mmc@fe330000', 's'),
                  ('/mmc@fe320000', 'status', 'okay', 's'),
                  ('/mmc@fe330000', 'status', 'okay', 's'),
                  ('/syscon@ff770000/phy@f780', 'status', 'okay', 's'),
                  ('/mmc@fe330000', 'bus-width', '8', 'u'),
                  ('/mmc@fe330000', 'max-frequency', '200000000', 'u'),
                  ('/hdmi@ff940000', 'status', 'okay', 's'),
                  ('/hdmi-sound', 'status', 'okay', 's'),
                  ('/gpu@ff9a0000', 'status', 'okay', 's'),
                  ('/ethernet@fe300000', 'status', 'okay', 's')]
    for node, prop, expected, kind in properties:
        actual = dtprop(path, node, prop, kind)
        check('dtb:' + node + ':' + prop, actual == expected, actual)
    for prop in ['mmc-hs400-1_8v', 'mmc-hs400-enhanced-strobe']:
        result = subprocess.run(['fdtget', str(path), '/mmc@fe330000', prop], capture_output=True)
        check('dtb-no-' + prop, result.returncode != 0, 'Property absent')
    result = subprocess.run(['fdtget', str(path), '/mmc@fe330000', 'mmc-hs200-1_8v'], capture_output=True)
    check('dtb-hs200', result.returncode == 0, 'HS200 enabled')


def read_sqfs(squashfs, name):
    return run(['unsquashfs', '-cat', str(squashfs), relative(name)])


def verify_secondary(squashfs, metadata, scratch):
    pinned(squashfs, metadata, 'secondary-input-hash')
    pinned(squashfs, SECONDARY, 'secondary-unmodified-official-43.1')
    summary = text(['unsquashfs', '-s', str(squashfs)])
    check('secondary-squashfs-zstd', 'Compression zstd' in summary, summary)
    with (scratch / 'secondary-full-read.log').open('wb') as log:
        result = subprocess.run(['unsquashfs', '-no-progress', '-processors', '2', '-pf', '/dev/null', str(squashfs)],
                                stdout=log, stderr=subprocess.STDOUT)
    check('secondary-full-decompression', result.returncode == 0,
          (scratch / 'secondary-full-read.log').read_text(errors='replace')[-2000:])
    core_root = scratch / 'secondary-cores'
    result = subprocess.run(['unsquashfs', '-no-progress', '-processors', '2', '-d', str(core_root),
                             str(squashfs), 'usr/lib/libretro'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    check('secondary-core-extraction', result.returncode == 0, result.stdout.decode(errors='replace')[-1000:])
    cores = sorted((core_root / 'usr/lib/libretro').glob('*_libretro.so'))
    check('secondary-103-official-cores', len(cores) == 103, len(cores))
    invalid = []
    for path in cores:
        with path.open('rb') as stream:
            data = stream.read(20)
        if (path.is_symlink() or data[:4] != b'\x7fELF' or len(data) != 20
                or data[4] != 2 or data[5] != 1 or struct.unpack_from('<H', data, 18)[0] != 183):
            invalid.append(path.name)
    check('secondary-all-cores-aarch64', not invalid, {'cores': len(cores), 'invalid': invalid})
    required = {'fceumm_libretro.so', 'gambatte_libretro.so', 'genesisplusgx_libretro.so',
                'mgba_libretro.so', 'snes9x_libretro.so', 'pcsx_rearmed_libretro.so',
                'mupen64plus-next_libretro.so', 'flycast_libretro.so', 'ppsspp_libretro.so',
                'fbneo_libretro.so', 'mame_libretro.so'}
    check('secondary-mainstream-cores-present', required <= {p.name for p in cores}, sorted(required))
    return len(cores)


def verify_rootfs(squashfs, inputs, scratch):
    pinned(squashfs, inputs['rootfs'], 'rootfs-pinned-hash')
    summary = text(['unsquashfs', '-s', str(squashfs)])
    check('rootfs-squashfs-zstd', 'Compression zstd' in summary, summary)
    with (scratch / 'rootfs-full-read.log').open('wb') as log:
        result = subprocess.run(['unsquashfs', '-no-progress', '-processors', '2', '-pf', '/dev/null', str(squashfs)],
                                stdout=log, stderr=subprocess.STDOUT)
    check('rootfs-full-decompression', result.returncode == 0,
          (scratch / 'rootfs-full-read.log').read_text(errors='replace')[-3000:])
    info = inputs.get('rootfs_checks')
    if info is None:
        info = json.loads((HERE / 'verification/rootfs-inputs.json').read_text())
    version = read_sqfs(squashfs, info.get('version_path', 'usr/share/batocera/batocera.version')).decode().strip()
    check('rootfs-version-is-43.1', re.match(r'^43\.1(?:\s|$|[-/])', version) is not None, version)
    arch = read_sqfs(squashfs, info.get('arch_path', 'usr/share/batocera/batocera.arch')).decode().strip()
    check('rootfs-platform-rk3399', arch == 'rk3399', arch)
    roles = set()
    for item in info['files']:
        name = relative(item['path'])
        data = read_sqfs(squashfs, name)
        actual = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        check('rootfs-file:' + name, actual['bytes'] == item['bytes'] and actual['sha256'] == item['sha256'], actual)
        if 'role' in item:
            roles.add(item['role'])
        if item.get('elf'):
            check('rootfs-aarch64:' + name, data[:4] == b'\x7fELF' and len(data) >= 20
                  and data[4] == 2 and data[5] == 1 and struct.unpack_from('<H', data, 18)[0] == 183,
                  'ELF64 little-endian AArch64')
        if item.get('upstream_sha256'):
            check('rootfs-original-43.1:' + name, actual['sha256'] == item['upstream_sha256'], item['upstream_sha256'])
        for token in item.get('contains', []):
            check('rootfs-token:' + name + ':' + token, token.encode() in data, token)
        if name.endswith('/firefly-select-hotkey'):
            ast.parse(data)
            check('select-script-python', True, name)
    required_roles = {'emulationstation', 'retroarch', 'panfrost', 'select-script', 'select-init', 'upgrade-guard'}
    check('rootfs-critical-roles-checked', required_roles <= roles, sorted(roles))
    select_path = info.get('select_config_path', 'usr/share/batocera/datainit/system/configs/emulationstation/es_input.cfg')
    config = ET.fromstring(read_sqfs(squashfs, select_path))
    eligible, mismatches = 0, []
    for controller in config.findall('inputConfig'):
        if controller.get('type') != 'joystick':
            continue
        selects = controller.findall("input[@name='select']")
        if len(selects) != 1:
            continue
        select = selects[0]
        if select.get('type') != 'button' or not select.get('id', '').isdigit() or select.get('value') != '1':
            continue
        eligible += 1
        hotkeys = controller.findall("input[@name='hotkey']")
        if len(hotkeys) != 1 or hotkeys[0].attrib != dict(select.attrib, name='hotkey'):
            mismatches.append(controller.get('deviceName', 'unknown'))
    check('select-hotkey-every-default-gamepad', eligible > 0 and not mismatches,
          {'eligible_profiles': eligible, 'mismatches': mismatches})
    actions = config.findall("inputAction[@type='onfinish']")
    hook = '/usr/bin/firefly-select-hotkey'
    check('select-onfinish-native-hook', bool(actions) and actions[0].findall('command')
          and (actions[0].findall('command')[-1].text or '').strip() == hook,
          'Select normalization runs last before native ES mapping reload')
    startup = read_sqfs(squashfs, 'etc/init.d/S30selecthotkey').decode()
    check('select-startup-invokes-normalizer', '/usr/bin/firefly-select-hotkey' in startup, startup)
    defaults = read_sqfs(squashfs, 'usr/share/batocera/datainit/system/batocera.conf').decode()
    check('generic-updates-disabled-by-default', re.search(r'^updates\.enabled=0$', defaults, re.M) is not None, 'updates.enabled=0')
    upgrader = read_sqfs(squashfs, 'usr/bin/batocera-upgrade').decode()
    check('firefly-upgrade-guard-present', 'Firefly-RK3399' in upgrader and 'firefly-rk3399' in upgrader, upgrader[:1600])
    listings = text(['unsquashfs', '-ll', str(squashfs), 'lib/modules']).splitlines()
    release = info['kernel_release']
    releases = set()
    for line in listings:
        match = re.search(r'\bsquashfs-root/lib/modules/([^/\s]+)', line)
        if match:
            releases.add(match.group(1))
    check('rootfs-only-matching-kernel-modules', releases == {release}, sorted(releases))
    check('rootfs-modules-pinned-nonempty', bool(info.get('modules')), len(info.get('modules', [])))
    module_tree = scratch / 'module-tree'
    result = subprocess.run(['unsquashfs', '-no-progress', '-processors', '2', '-d', str(module_tree),
                             str(squashfs), 'lib/modules'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    check('rootfs-module-tree-extraction', result.returncode == 0, result.stdout.decode(errors='replace')[-1000:])
    expected_modules = {relative(item['path']): item for item in info['modules']}
    actual_paths = {p.relative_to(module_tree).as_posix() for p in (module_tree / 'lib/modules').rglob('*')}
    check('rootfs-module-tree-exact-paths', actual_paths == set(expected_modules),
          {'actual': len(actual_paths), 'expected': len(expected_modules),
           'extra': sorted(actual_paths - set(expected_modules)), 'missing': sorted(set(expected_modules) - actual_paths)})
    mismatches, vermagic_errors, checked_files = [], [], 0
    for name, item in expected_modules.items():
        path = module_tree / name
        valid = name == 'lib/modules/' + release or name.startswith('lib/modules/' + release + '/')
        kind = item.get('type', 'file')
        if kind == 'symlink':
            valid = valid and path.is_symlink() and str(path.readlink()) == item['target']
        elif kind == 'directory':
            valid = valid and path.is_dir() and not path.is_symlink()
        else:
            valid = valid and not path.is_symlink() and path.is_file() and path.stat().st_size == item['bytes'] and sha(path) == item['sha256']
            checked_files += 1
            if valid and '.ko' in path.name:
                # Kernel modules are uncompressed in this pinned BSP. Reading
                # .modinfo in the ELF itself checks every module without loading it.
                data = path.read_bytes()
                match = re.search(rb'(?:^|\x00)vermagic=([^\x00]+)', data)
                if not match or match.group(1).split()[0].decode() != release:
                    vermagic_errors.append(name)
        if not valid:
            mismatches.append(name)
    check('rootfs-entire-module-tree-content', not mismatches,
          {'regular_files_hashed': checked_files, 'entries': len(expected_modules), 'mismatches': mismatches})
    check('rootfs-all-module-vermagic', not vermagic_errors,
          {'kernel_release': release, 'invalid_modules': vermagic_errors})
    for name in info.get('absent_paths', []):
        result = subprocess.run(['unsquashfs', '-cat', str(squashfs), relative(name)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        check('rootfs-removed:' + name, result.returncode != 0, result.stderr.decode(errors='replace')[-400:])
    return version, eligible


def verify_installer_script(script, raw_name):
    syntax = ast.parse(script.read_bytes())
    check('installer-python-syntax', True, 'Python parser accepted complete script')
    image_defaults = [keyword.value for node in ast.walk(syntax) if isinstance(node, ast.Call)
                      and isinstance(node.func, ast.Attribute) and node.func.attr == 'add_argument'
                      and any(isinstance(arg, ast.Constant) and arg.value == '--image' for arg in node.args)
                      for keyword in node.keywords if keyword.arg == 'default']
    check('installer-default-matches-43.1-payload', len(image_defaults) == 1
          and any(isinstance(node, ast.Constant) and node.value == raw_name + '.gz'
                  for node in ast.walk(image_defaults[0])), raw_name + '.gz')


def verify_initrd(initrd, scratch):
    data = run(['lz4', '-dc', str(initrd)])
    result = subprocess.run(['cpio', '--extract', '--to-stdout', 'init'], input=data,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=scratch)
    check('initrd-init-extraction', result.returncode == 0, result.stderr.decode(errors='replace').strip())
    actual = hashlib.sha256(result.stdout).hexdigest()
    check('initrd-pinned-official-43.1-init', actual == '7bf275af5c06ba9228da99e6bc77c03a28874648ea0ea0a4b7ca317928ec38b8', actual)
    text_init = result.stdout.decode()
    check('initrd-fixed-medium-root-supported', 'dev=' in text_init and '/new_root' in text_init
          and 'exec switch_root /new_root /sbin/init' in text_init, 'Pinned root parameter parser and switch_root')
    primary_mount = 'mount /boot_root/boot/batocera /overlay_root/base || return 1'
    secondary_mount = 'mount /boot_root/boot/rufomaculata /overlay_root/base2 || return 1'
    check('initrd-dual-layer-mounts', primary_mount in text_init and secondary_mount in text_init,
          'Official primary and rufomaculata secondary SquashFS mounts')
    check('initrd-primary-precedes-secondary', 'EXTRALAYERS=":/overlay_root/base2"' in text_init
          and 'lowerdir=/overlay_root/base$EXTRALAYERS,upperdir=' in text_init,
          'Overlay lowerdir=primary:secondary, primary board adaptation wins')
    listing = subprocess.run(['cpio', '--list'], input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    paths = listing.stdout.decode().splitlines()
    check('initrd-no-kernel-modules', listing.returncode == 0 and not any('lib/modules' in p for p in paths),
          {'archive_entries': len(paths), 'kernel_modules': 0})
    busybox = subprocess.run(['cpio', '--extract', '--to-stdout', 'bin/busybox'], input=data,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=scratch)
    elf = busybox.stdout
    check('initrd-aarch64-busybox', busybox.returncode == 0 and len(elf) >= 64 and elf[:4] == b'\x7fELF'
          and elf[4:6] == bytes([2, 1]) and struct.unpack_from('<H', elf, 18)[0] == 183, 'AArch64 initrd BusyBox')
    phoff, phsize, phnum = struct.unpack_from('<Q', elf, 32)[0], *struct.unpack_from('<HH', elf, 54)
    headers = [struct.unpack_from('<I', elf, phoff + n * phsize)[0] for n in range(phnum)]
    check('initrd-busybox-static', 2 not in headers and 3 not in headers, {'program_header_types': headers})
    config = (ROOT / 'source/kernel/base-kernel.config').read_text().splitlines()
    required = ['CONFIG_EXT4_FS=y', 'CONFIG_BLK_DEV_LOOP=y', 'CONFIG_SQUASHFS=y', 'CONFIG_OVERLAY_FS=y']
    check('kernel-required-filesystems-built-in', all(line in config for line in required), required)


def main(args):
    ordinary(args.image)
    image = args.image.resolve()
    inputs = json.loads(args.inputs.read_text())
    check('input-version-43.1', inputs.get('version') == '43.1', inputs.get('version'))
    geometry = GEOMETRIES[args.mode]
    check('image-name', image.name == geometry['name'], image.name)
    check('image-size', image.stat().st_size == geometry['bytes'], image.stat().st_size)
    image_hash = sha(image)
    sidecar = json.loads(image.with_suffix('.manifest.json').read_text())
    check('sidecar-release', sidecar.get('release') == '43.1-firefly-emmc-test1', sidecar.get('release'))
    check('sidecar-board-hotkey', sidecar.get('board') == 'firefly-rk3399' and sidecar.get('hotkey') == 'select',
          {'board': sidecar.get('board'), 'hotkey': sidecar.get('hotkey')})
    check('sidecar-inputs-sha256', sidecar.get('inputs_sha256') == sha(args.inputs), sha(args.inputs))
    for key, expected in [('image', image.name), ('mode', args.mode), ('bytes', geometry['bytes']),
                          ('sha256', image_hash), ('root_device', geometry['root']), ('version', '43.1')]:
        check('sidecar-' + key, sidecar.get(key) == expected, sidecar.get(key))
    scratch_parent = args.scratch or HERE / 'verification/scratch'
    scratch_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='v431-' + args.mode + '-', dir=scratch_parent) as directory:
        scratch = Path(directory)
        with image.open('rb') as stream:
            partitions = verify_mbr(stream, args.mode)
            declared_parts = [{'type': kind, 'start_lba': start, 'sectors': length} for kind, start, length in partitions]
            check('sidecar-partitions', sidecar.get('partitions') == declared_parts, sidecar.get('partitions'))
            check('sidecar-boot-assets', sidecar.get('boot_assets') == inputs['boot_assets'][args.mode], sidecar.get('boot_assets'))
            verify_boot(stream, args.mode, scratch)
            p1_offset, p1_bytes = partitions[0][1] * SECTOR, partitions[0][2] * SECTOR
            p2_offset, p2_bytes = partitions[1][1] * SECTOR, partitions[1][2] * SECTOR
            bpb = read_at(stream, p1_offset, 512)
            sector_size, total = struct.unpack_from('<H', bpb, 11)[0], struct.unpack_from('<I', bpb, 32)[0]
            check('fat32-bpb', bpb[510:] == b'\x55\xaa' and bpb[82:90] == b'FAT32   '
                  and sector_size == SECTOR and 0 < total <= geometry['fat_sectors'],
                  {'bytes_per_sector': sector_size, 'total_sectors': total})
            check('fat32-label', bpb[71:82].rstrip() == b'BATOCERA', bpb[71:82].decode())
            tail_bytes = p1_bytes - total * SECTOR
            check('fat32-tail-zero', not any(read_at(stream, p1_offset + total * SECTOR, tail_bytes)), tail_bytes)
            filesystem = scratch / 'fat32.img'
            copy_region(stream, p1_offset, p1_bytes, filesystem)
            result = subprocess.run(['fsck.fat', '-n', '-v', str(filesystem)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            check('fat32-fsck-readonly', result.returncode == 0, result.stdout.decode(errors='replace')[-4000:])
            filesystem.unlink()
            sb = read_at(stream, p2_offset + 1024, 1024)
            check('share-ext4', sb[56:58] == b'\x53\xef' and sb[120:136].rstrip(b'\0') == b'SHARE', 'ext4 SHARE')
            share_hash = region_hash(stream, p2_offset, p2_bytes)
            check('share-pinned-hash', share_hash == inputs['components']['share']['sha256'] and p2_bytes == inputs['components']['share']['bytes'], share_hash)
        def extract(name):
            name = relative(name)
            path = scratch / 'fat' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            text(['mcopy', '-i', f'{image}@@{p1_offset}', '::/' + name, str(path)])
            return path
        extlinux_file = extract('extlinux/extlinux.conf')
        pinned(extlinux_file, inputs['boot_assets'][args.mode]['extlinux'], 'extlinux-pinned-file')
        extlinux = extlinux_file.read_text()
        values = {}
        for line in extlinux.splitlines():
            words = line.strip().split(None, 1)
            if len(words) == 2 and words[0] in {'LINUX', 'INITRD', 'FDT', 'APPEND'}:
                check('extlinux-single-' + words[0], words[0] not in values, words[1])
                values[words[0]] = words[1]
        expected_paths = {'LINUX': '/boot/linux', 'INITRD': '/boot/initrd.lz4', 'FDT': '/boot/rk3399-firefly-batocera-emmc.dtb'}
        for key, expected in expected_paths.items():
            check('extlinux-' + key, values.get(key) == expected, values.get(key))
        tokens = values.get('APPEND', '').split()
        check('extlinux-medium-root', [word for word in tokens if word.startswith('dev=')] == ['dev=' + geometry['root']], tokens)
        check('extlinux-no-label-root', not any(word.startswith('label=') for word in tokens), tokens)
        check('extlinux-serial-console', 'console=ttyS2,1500000n8' in tokens, tokens)
        pinned(extract('boot/linux'), inputs['components']['kernel'], 'linux-kernel')
        initrd = extract('boot/initrd.lz4')
        pinned(initrd, inputs['components']['initrd'], 'linux-initrd')
        verify_initrd(initrd, scratch)
        verify_dtb(extract('boot/rk3399-firefly-batocera-emmc.dtb'), inputs['components']['dtb'])
        check('board-identity', extract('boot/batocera.board').read_text().strip() == 'firefly-rk3399', 'firefly-rk3399')
        for key, name in [('board', 'boot/batocera.board'), ('boot_config', 'batocera-boot.conf'), ('collect_logs', 'collect-logs.sh')]:
            pinned(extract(name) if key != 'board' else scratch / 'fat/boot/batocera.board', inputs['components'][key], 'fat-component:' + key)
        for key, name in [('install', 'FIREFLY-README.txt'), ('hotkey', 'SELECT-HOTKEY.txt')]:
            pinned(extract(name), inputs['documents'][key], 'fat-document:' + key)
        boot_listing = text(['mdir', '-b', '-i', f'{image}@@{p1_offset}', '::/boot']).splitlines()
        forbidden = {'batocera.update', 'rufomaculata.update', 'overlay'}
        check('no-stale-rootfs-or-saved-overlay', not any(PurePosixPath(line.strip()).name in forbidden for line in boot_listing), boot_listing)
        squashfs = extract('boot/batocera')
        version, profiles = verify_rootfs(squashfs, inputs, scratch)
        core_count = verify_secondary(extract('boot/rufomaculata'), inputs['components']['secondary'], scratch)
        check('sidecar-rootfs-hash', sidecar.get('rootfs_sha256') == inputs['rootfs']['sha256'], sidecar.get('rootfs_sha256'))
        check('sidecar-secondary-hash', sidecar.get('secondary_sha256') == inputs['components']['secondary']['sha256'], sidecar.get('secondary_sha256'))
        if args.mode == 'installer':
            payload = json.loads(extract('emmc/manifest.json').read_text())
            check('embedded-manifest-sidecar', payload == sidecar.get('payload'), payload)
            check('embedded-board-medium', payload.get('board') == 'firefly-rk3399' and payload.get('medium') == 'emmc', payload)
            raw_name = GEOMETRIES['emmc']['name']
            check('embedded-raw-name', payload['image']['name'] == raw_name, payload['image']['name'])
            check('embedded-compressed-name', payload['compressed']['name'] == raw_name + '.gz', payload['compressed']['name'])
            embedded = extract('emmc/' + payload['compressed']['name'])
            compressed_meta = pinned(embedded, payload['compressed'], 'embedded-compressed-hash')
            external_gz = image.parent / payload['compressed']['name']
            pinned(external_gz, compressed_meta, 'external-emmc-compressed-match')
            raw_sha, raw_bytes = hash_gzip(embedded)
            check('embedded-full-decompression', raw_bytes == GEOMETRIES['emmc']['bytes'] == payload['image']['bytes']
                  and raw_sha == payload['image']['sha256'], {'bytes': raw_bytes, 'sha256': raw_sha})
            pinned(image.parent / raw_name, {'bytes': raw_bytes, 'sha256': raw_sha}, 'external-emmc-raw-match')
            script = extract('emmc/install-to-emmc.py')
            actual_script = pinned(script, inputs['components']['installer'], 'installer-script')
            check('sidecar-installer-script', sidecar.get('installer_script_sha256') == actual_script['sha256'], actual_script['sha256'])
            verify_installer_script(script, raw_name)
    compressed = args.gzip or Path(str(image) + '.gz')
    compressed_hash = None
    if not args.skip_gzip:
        ordinary(compressed)
        raw_sha, raw_bytes = hash_gzip(compressed)
        check('outer-gzip-full-decompression', raw_sha == image_hash and raw_bytes == geometry['bytes'], {'sha256': raw_sha, 'bytes': raw_bytes})
        compressed_hash = sha(compressed)
    sums = {}
    for line in (image.parent / 'SHA256SUMS').read_text().splitlines():
        if not line.strip():
            continue
        value, name = line.split(None, 1)
        check('checksum-entry-format:' + name, re.fullmatch(r'[0-9a-f]{64}', value) is not None, value)
        sums[name.lstrip('*')] = value
    check('published-raw-sha256', sums.get(image.name) == image_hash, image_hash)
    if not args.skip_gzip:
        check('published-compressed-sha256', sums.get(compressed.name) == compressed_hash, compressed_hash)
    return {'mode': args.mode, 'image': str(image), 'image_sha256': image_hash,
            'compressed': None if args.skip_gzip else str(compressed), 'compressed_sha256': compressed_hash,
            'system_squashfs_sha256': inputs['rootfs']['sha256'], 'batocera_version': version,
            'select_gamepad_profiles': profiles, 'secondary_libretro_cores': core_count,
            'secondary_squashfs_sha256': inputs['components']['secondary']['sha256'], 'gzip_checked': not args.skip_gzip,
            'inputs_sha256': sha(args.inputs),
            'rootfs_checks_sha256': None if inputs.get('rootfs_checks') else sha(HERE / 'verification/rootfs-inputs.json')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', required=True, choices=GEOMETRIES)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--gzip', type=Path)
    parser.add_argument('--skip-gzip', action='store_true')
    parser.add_argument('--inputs', type=Path, default=HERE / 'inputs.json')
    parser.add_argument('--scratch', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = {}
    try:
        report.update(main(args))
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
    report.update({'checks': checks, 'passed': sum(item['pass'] for item in checks), 'total': len(checks),
                   'result': 'FAIL' if 'error' in report else 'PASS'})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(f"Image verification: {report['passed']}/{report['total']} {report['result']}")
    if report.get('error'):
        print(report['error'])
        raise SystemExit(1)
