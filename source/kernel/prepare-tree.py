#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare the exact Linux 6.6.27 DTS dependency closure and Batocera40 hunks."""
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
src = pathlib.Path(__file__).resolve().parent
out = pathlib.Path(sys.argv[1]).resolve()
manifest = json.loads((src / 'manifest.json').read_text())
for name, entry in manifest.get('config_snapshots', {}).items():
    if hashlib.sha256((src / name).read_bytes()).hexdigest() != entry['sha256']:
        raise SystemExit('Configuration hash mismatch: ' + name)
reference = manifest['additional_board_reference']
if hashlib.sha256((src / 'armbian-firefly-board-reference.patch').read_bytes()).hexdigest() != reference['sha256']:
    raise SystemExit('Armbian reference hash mismatch')
for name, entry in manifest['linux_sources'].items():
    data = (src / 'linux-6.6.27' / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != entry['sha256']:
        raise SystemExit('Source hash mismatch: ' + name)
    dest = out / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink():
        dest.unlink()
    if 'symlink_target' in entry:
        dest.unlink(missing_ok=True)
        dest.symlink_to(entry['symlink_target'])
    else:
        dest.write_bytes(data)
applied = []
for entry in manifest['patch_inventory']:
    patch = src / 'batocera-patches' / entry['file']
    data = patch.read_bytes()
    if hashlib.sha256(data).hexdigest() != entry['sha256']:
        raise SystemExit('Patch hash mismatch: ' + entry['file'])
    if not entry['affects_dependency']:
        continue
    selected = []
    for part in re.split(r'(?=^diff --git )', data.decode(), flags=re.M):
        header = re.match(r'diff --git a/\S+ b/(\S+)', part)
        if header and header[1] in entry['affects_dependency']:
            selected.append(part.split('\n-- \n', 1)[0].rstrip() + '\n')
    if len(selected) != len(entry['affects_dependency']):
        raise SystemExit('Incomplete patch selection: ' + entry['file'])
    subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-d', str(out)],
                   input=''.join(selected).encode(), check=True)
    applied.append({'file': entry['file'], 'paths': entry['affects_dependency']})
for p in src.glob('rk3399-firefly-batocera*.dts'):
    shutil.copyfile(p, out / 'arch/arm64/boot/dts/rockchip' / p.name)
(out / 'applied-patches.json').write_text(json.dumps(applied, indent=2) + '\n')
print('Prepared', len(manifest['linux_sources']), 'sources and', len(applied), 'patch files')
