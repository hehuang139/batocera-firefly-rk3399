#!/usr/bin/env python3
"""Inspect compiled boot assets and their placement, without touching hardware."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'work/boot'
UBOOT = WORK / 'uboot'
ASSETS = WORK / 'assets'
checks = []


def check(name, ok, detail):
    checks.append({'name': name, 'pass': bool(ok), 'detail': detail})
    if not ok:
        raise RuntimeError(f'{name}: {detail}')


def fdt(path, node, prop):
    return subprocess.check_output(['fdtget', str(path), node, prop], text=True).strip()


config = (UBOOT / '.config').read_text()
for key in ['CONFIG_ARM64=y', 'CONFIG_ROCKCHIP_RK3399=y',
            'CONFIG_DEFAULT_DEVICE_TREE="rk3399-firefly"',
            'CONFIG_TPL=y', 'CONFIG_SPL=y', 'CONFIG_ENV_IS_NOWHERE=y',
            '# CONFIG_ENV_IS_IN_MMC is not set', '# CONFIG_VIDEO is not set',
            'CONFIG_BAUDRATE=1500000']:
    check('config:' + key.split('=')[0], key in config.splitlines(), key)
check('no-external-ddr-binary', 'CONFIG_ROCKCHIP_EXTERNAL_TPL=y' not in config, 'Use built-in DDR3 TPL')
check('no-silent-console', 'CONFIG_SILENT_CONSOLE=y' not in config, 'UART messages enabled')
for target, node, prop, expected in [
    ('u-boot.dtb', '/aliases', 'mmc1', '/mmc@fe320000'),
    ('u-boot.dtb', '/', 'compatible', 'firefly,firefly-rk3399 rockchip,rk3399'),
    ('spl/u-boot-spl.dtb', '/chosen', 'u-boot,spl-boot-order', '/mmc@fe320000'),
]:
    value = fdt(UBOOT / target, node, prop)
    check('dt:' + prop, value == expected, value)

uboot_bin = (UBOOT / 'u-boot.bin').read_bytes()
check('boot-targets-tf-only', b'boot_targets=mmc1\0' in uboot_bin,
      'Built U-Boot environment boot_targets=mmc1')
tpl = (UBOOT / 'tpl/u-boot-tpl.bin').read_bytes()
spl = (UBOOT / 'spl/u-boot-spl.bin').read_bytes()
check('compiled-ddr-tpl-present', len(tpl) > 4096, f'{len(tpl)} bytes')
check('compiled-spl-present', len(spl) > 4096, f'{len(spl)} bytes')
ddr = [int(value) for value in subprocess.check_output(
    ['fdtget', '-t', 'u', str(UBOOT / 'tpl/u-boot-tpl.dtb'), '/dmc', 'rockchip,sdram-params'],
    text=True).split()]
check('compiled-ddr-type-and-rate', ddr[34:36] == [800, 3],
      f'frequency={ddr[34]} MHz, type={ddr[35]} (DDR3)')
for name in ['rk3399m0', 'rk3399m0pmu']:
    data = (WORK / f'tfa/rk3399/release/m0/{name}.elf').read_bytes()
    check('cortex-m0:' + name,
          data[:5] == b'\x7fELF\x01' and int.from_bytes(data[16:18], 'little') == 2
          and int.from_bytes(data[18:20], 'little') == 40,
          'ELF32 / ET_EXEC / EM_ARM, fixed-address non-PIE firmware')

combined = (ASSETS / 'u-boot-rockchip.bin').read_bytes()
idb = (ASSETS / 'idbloader.img').read_bytes()
fit = (ASSETS / 'u-boot.itb').read_bytes()
fit_offset = 8388608 - 32768
check('combined-idb-offset', combined[:len(idb)] == idb, 'LBA64 when combined image is written at LBA64')
check('combined-fit-offset', combined[fit_offset:fit_offset + len(fit)] == fit, 'FIT at absolute LBA16384')
check('idb-before-env-gap', len(idb) < 4 * 1024 * 1024 - 32768, f'{len(idb)} bytes')
check('fit-before-16MiB', len(fit) < 8 * 1024 * 1024, f'{len(fit)} bytes')
check('fit-magic', fit[:4] == bytes.fromhex('d00dfeed'), fit[:4].hex())
check('idb-contains-compiled-tpl', idb[2048:2052] == b'RK33' and idb[2052:2048 + len(tpl)] == tpl[4:],
      'Rockchip boot marker replaces the first TPL instruction; remaining bytes match')
check('idb-contains-compiled-spl', spl in idb, 'Full SPL binary is embedded')
check('fit-contains-compiled-uboot', (UBOOT / 'u-boot-nodtb.bin').read_bytes() in fit,
      'Full U-Boot proper binary is embedded')
check('fit-contains-firefly-control-dtb', (UBOOT / 'u-boot.dtb').read_bytes() in fit,
      'Full compiled Firefly U-Boot DTB is embedded')
bl31 = (ASSETS / 'bl31.elf').read_bytes()
check('bl31-aarch64-elf', bl31[:5] == b'\x7fELF\x02' and int.from_bytes(bl31[18:20], 'little') == 183,
      'ELF64 / EM_AARCH64')
fit_list = (WORK / 'fit-list.txt').read_text()
check('fit-atf-payload', 'ARM Trusted Firmware' in fit_list and 'rk3399-firefly' in fit_list,
      'FIT lists TF-A and Firefly board FDT')

manifest = {
    'board': 'Firefly-RK3399 original DDR3 board',
    'medium': 'TF/SD',
    'uboot_version': 'v2024.01',
    'tf_a_version': 'v2.10',
    'upstream_urls': {
        'u-boot-v2024.01.tar.gz': 'https://github.com/u-boot/u-boot/archive/refs/tags/v2024.01.tar.gz',
        'arm-trusted-firmware-v2.10.tar.gz': 'https://github.com/ARM-software/arm-trusted-firmware/archive/refs/tags/v2.10.tar.gz',
    },
    'source_date_epoch': 1704700800,
    'ddr': 'mainline U-Boot TPL, rk3399-sdram-ddr3-1600.dtsi, DDR3 800MHz',
    'boot_policy': {'spl': '/mmc@fe320000 only', 'uboot': 'mmc1 only', 'environment': 'nowhere'},
    'placement_bytes': {'idbloader.img': 32768, 'u-boot.itb': 8388608, 'u-boot-rockchip.bin': 32768},
    'sources': [
        {'path': str(p.relative_to(ROOT)), 'size': p.stat().st_size,
         'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in sorted((ROOT / 'source/boot').glob('*.tar.gz'))
    ],
    'assets': [
        {'name': p.name, 'size': p.stat().st_size,
         'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in sorted(ASSETS.iterdir()) if p.is_file() and p.name != 'SHA256SUMS'
    ],
    'checks': checks,
    'result': 'PASS',
}
(ROOT / 'source/boot/manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
(ASSETS / 'SHA256SUMS').write_text(''.join(f'{item["sha256"]}  {item["name"]}\n' for item in manifest['assets']))
print(f'Boot assets validated: {len(checks)} PASS')
