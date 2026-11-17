#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise actual split/join file handling with compact deterministic fixtures."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('split_release', HERE / 'split-release.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.LIMIT = 37
checks = []
with tempfile.TemporaryDirectory(prefix='release-parts-') as temporary:
    root = Path(temporary)
    image = root / 'fixture.img.gz'; image.write_bytes(bytes(range(250)))
    parts = root / 'parts'
    with patch.object(sys, 'argv', ['split-release.py', str(image), str(parts)]): m.main()
    manifest = parts / (image.name + '.parts.json')
    result = subprocess.run([sys.executable, str(HERE / 'join-firmware.py'), str(manifest)], capture_output=True)
    assert result.returncode == 0 and (parts / image.name).read_bytes() == image.read_bytes()
    checks.append('actual split and join preserves complete input bytes')
    result = subprocess.run([sys.executable, str(HERE / 'join-firmware.py'), str(manifest)], capture_output=True)
    assert result.returncode != 0
    checks.append('existing output is preserved')
    (parts / image.name).unlink()
    bad = parts / (image.name + '.part001'); old = bad.read_bytes(); bad.write_bytes(b'X' + old[1:])
    result = subprocess.run([sys.executable, str(HERE / 'join-firmware.py'), str(manifest)], capture_output=True)
    assert result.returncode != 0 and not (parts / image.name).exists()
    checks.append('corrupt part rejected before creating output')
    bad.write_bytes(old)
    obj = json.loads(manifest.read_text()); obj['parts'].reverse(); manifest.write_text(json.dumps(obj))
    result = subprocess.run([sys.executable, str(HERE / 'join-firmware.py'), str(manifest)], capture_output=True)
    assert result.returncode != 0 and not (parts / image.name).exists()
    checks.append('wrong part order rejected')
report = {'result': 'PASS', 'count': len(checks), 'checks': checks}
(HERE / 'tests/release-parts-validation.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
