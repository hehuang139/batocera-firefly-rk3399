#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Record and prepare the exact 43.1 donor delta before applying it."""
import argparse
import sys
sys.dont_write_bytecode = True
import importlib.machinery
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('firefly_apply', HERE / 'apply.py')
apply = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apply)
GUARD = '''# Firefly port: generic upstream images omit this board's DTB and boot configuration.
FIREFLY_MODEL=$(tr -d '\\000' < /sys/firmware/devicetree/base/model 2>/dev/null || true)
FIREFLY_BOARD=$(cat /boot/boot/batocera.board 2>/dev/null || true)
if [ "$FIREFLY_MODEL" = "Firefly-RK3399 Board" ] || [ "$FIREFLY_BOARD" = firefly-rk3399 ]; then
    echo "Firefly RK3399 requires a matching Firefly release image; the generic online updater is disabled." >&2
    exit 1
fi

'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rootfs', type=Path, required=True)
    parser.add_argument('--bsp-rootfs', type=Path, required=True)
    parser.add_argument('--rk3399-defaults', type=Path, required=True)
    args = parser.parse_args()
    root, bsp = args.rootfs.resolve(), args.bsp_rootfs.resolve()
    if (HERE / 'provenance.json').exists():
        raise ValueError('Provenance already frozen; do not regenerate from an adapted tree')
    version = (root / 'usr/share/batocera/batocera.version').read_text()
    if version != '43.1 2026/06/01 19:14\n':
        raise ValueError('Unexpected donor version')
    loader = importlib.machinery.SourceFileLoader('select_hotkey', str(HERE / 'overlay/usr/bin/firefly-select-hotkey'))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    records = []

    def put(relative, data, mode=None):
        src = root / relative
        dest = HERE / 'overlay' / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        dest.chmod(mode if mode is not None else int(apply.identity(src)['mode'], 8))

    put('etc/inittab', (root / 'etc/inittab').read_bytes().replace(b'ttyAML0 115200', b'ttyS2 1500000'))
    put('usr/share/batocera/batocera.arch', b'rk3399')
    put('usr/share/batocera/configgen/configgen-defaults-arch.yml', args.rk3399_defaults.read_bytes())
    upgrade = (root / 'usr/bin/batocera-upgrade').read_bytes()
    assert upgrade.startswith(b'#!/bin/bash\n')
    put('usr/bin/batocera-upgrade', b'#!/bin/bash\n\n' + GUARD.encode() + upgrade[len(b'#!/bin/bash\n'):])
    config = (root / 'usr/share/batocera/datainit/system/batocera.conf').read_bytes()
    assert config.count(b'\nupdates.enabled=1\n') == 1
    put('usr/share/batocera/datainit/system/batocera.conf', config.replace(b'\nupdates.enabled=1\n', b'\nupdates.enabled=0\n'))
    put('usr/share/batocera/sysconfigs/batocera.conf.Firefly_RK3399_Board', b'# Firefly RK3399: use the 43.1 PipeWire RK3399 automatic HDMI route.\naudio.device=auto\naudio.profile=auto\n', 0o644)
    shared = 'usr/share/emulationstation/es_input.cfg'
    normalized, count = module.transform((root / shared).read_bytes())
    put(shared, normalized)
    for source in sorted((HERE / 'overlay').rglob('*')):
        if source.is_file():
            relative = source.relative_to(HERE / 'overlay').as_posix()
            records.append({'path': relative, 'before': apply.identity(root / relative), 'after': apply.identity(source)})
    records.append({'path': 'etc/init.d/S02overclock', 'before': apply.identity(root / 'etc/init.d/S02overclock'), 'after': None})
    for filename in ['BCM4356A2.hcd', 'brcmfmac4356-sdio.bin', 'brcmfmac4356-sdio.txt', 'brcmfmac4356-sdio.clm_blob']:
        relative = 'lib/firmware/brcm/' + filename
        records.append({'path': relative, 'before': apply.identity(root / relative), 'after': apply.identity(bsp / relative), 'source': relative})
    invariants = []
    for relative in ['usr/share/batocera/batocera.version', 'usr/bin/emulationstation', 'usr/bin/retroarch', 'usr/bin/python3.12', 'usr/bin/batocera-audio', 'etc/init.d/S27audioconfig', 'etc/init.d/S32bluetooth', 'etc/init.d/S14labwc', 'usr/bin/labwc-launch', 'etc/init.d/S90hotkeygen']:
        current = apply.identity(root / relative)
        if current is not None:
            invariants.append({'path': relative, 'identity': current})
    # Mesa's main shared implementation must remain from the 43.1 release.
    for file in sorted((root / 'usr/lib').glob('libgallium*')):
        invariants.append({'path': file.relative_to(root).as_posix(), 'identity': apply.identity(file)})
    manifest = {'schema': 1, 'version_text': version, 'arch': 'rk3399', 'kernel': '6.6.27',
                'donor': {'board': 'odroidn2plus', 'release': '43.1', 'boot_tar_sha256': '9151efb125368e19e07733fbda9f2ccece3a01186156f7d6c29fc69abfec11e5', 'url': 'https://mirrors.o2switch.fr/batocera/odroidn2plus/stable/last/boot.tar.xz'},
                'select_default_changed_entries': count,
                'files': records, 'invariants': invariants,
                'donor_modules': apply.inventory(root, 'lib/modules'),
                'bsp_modules': apply.inventory(bsp, 'lib/modules')}
    (HERE / 'provenance.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'files': len(records), 'select_changed_entries': count, 'invariants': len(invariants)}))


if __name__ == '__main__':
    main()
