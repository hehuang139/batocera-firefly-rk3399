#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify the sole manifest change after fixing the TF installer default."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(8388608), b''):
            h.update(data)
    return h.hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    before_path = ROOT / 'source/v431/provenance/inputs-before-installer-fix.json'
    now_path = ROOT / 'source/v431/inputs.json'
    original_path = ROOT / 'outputs/v431/validation/emmc-image.json'
    before, now, original = [json.loads(p.read_text()) for p in [before_path, now_path, original_path]]
    assert original['result'] == 'PASS' and original['gzip_checked']
    assert original['inputs_sha256'] == sha(before_path)
    assert before['components']['installer']['bytes'] == 16247
    assert now['components']['installer']['bytes'] == 16248
    amended = copy.deepcopy(before)
    amended['components']['installer'] = now['components']['installer']
    assert amended == now, 'Unexpected inputs change beyond installer filename fix'
    script_item = now['components']['installer']
    script = ROOT / script_item['path']
    assert script.stat().st_size == script_item['bytes'] and sha(script) == script_item['sha256']
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location('verifier', ROOT / 'source/v431/verify-image.py')
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    name = verifier.GEOMETRIES['emmc']['name']
    verifier.verify_installer_script(script, name)
    image = ROOT / 'outputs/v431' / name
    compressed = Path(str(image) + '.gz')
    current_raw, current_gzip = sha(image), sha(compressed)
    assert current_raw == original['image_sha256']
    assert current_gzip == original['compressed_sha256']
    sidecar_path = image.with_suffix('.manifest.json')
    sidecar = json.loads(sidecar_path.read_text())
    assert sidecar['inputs_sha256'] == sha(now_path)
    assert sidecar['sha256'] == current_raw
    assert sidecar['bytes'] == image.stat().st_size == verifier.GEOMETRIES['emmc']['bytes']
    assert sidecar['rootfs_sha256'] == now['rootfs']['sha256'] == original['system_squashfs_sha256']
    assert sidecar['secondary_sha256'] == now['components']['secondary']['sha256'] == original['secondary_squashfs_sha256']
    report = {'result':'PASS', 'original_full_verification_sha256':sha(original_path),
              'original_full_checks':original['total'], 'original_inputs_sha256':sha(before_path),
              'current_inputs_sha256':sha(now_path),
              'sole_change':'TF installer default image basename changed from batocera40 to batocera431; installer bytes/hash updated',
              'image_sha256':current_raw,'compressed_sha256':current_gzip,
              'image_bytes':image.stat().st_size,'compressed_bytes':compressed.stat().st_size,
              'sidecar_sha256':sha(sidecar_path), 'installer_checks':verifier.checks,
              'verification':'Rehashed complete existing raw/gzip files and matched original 166-check full verification; current sidecar references current inputs.'}
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'result':'PASS','original_full_checks':original['total'], 'inputs_sha256':report['current_inputs_sha256']}))

if __name__ == '__main__':
    main()
