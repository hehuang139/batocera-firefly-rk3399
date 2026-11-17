#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Split oversized gzip images for GitHub Release and verify every part on readback."""
import argparse
import hashlib
import json
from pathlib import Path
import stat

LIMIT = 1800 * 1024 * 1024


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('image', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    if a.image.is_symlink() or not stat.S_ISREG(a.image.stat().st_mode):
        p.error('Expected an ordinary compressed image')
    a.output.mkdir(parents=True, exist_ok=True)
    total, expected = 0, hashlib.sha256()
    parts = []
    try:
        with a.image.open('rb') as source:
            index = 1
            while total < a.image.stat().st_size:
                name = a.image.name + '.part' + str(index).zfill(3)
                target = a.output / name
                h, length = hashlib.sha256(), 0
                with target.open('xb') as stream:
                    while length < LIMIT:
                        block = source.read(min(8388608, LIMIT - length))
                        if not block: break
                        stream.write(block); h.update(block); expected.update(block); length += len(block)
                total += length
                parts.append({'name': name, 'bytes': length, 'sha256': h.hexdigest()})
                index += 1
        actual = hashlib.sha256()
        for item in parts:
            h = hashlib.sha256()
            with (a.output / item['name']).open('rb') as stream:
                for block in iter(lambda: stream.read(8388608), b''):
                    h.update(block); actual.update(block)
            if h.hexdigest() != item['sha256']: raise ValueError('Part readback mismatch')
        if total != a.image.stat().st_size or actual.hexdigest() != expected.hexdigest():
            raise ValueError('Joined image readback mismatch')
        report = {'result': 'PASS', 'image': {'name': a.image.name, 'bytes': total, 'sha256': actual.hexdigest()},
                  'parts': parts, 'max_part_bytes': LIMIT}
        path = a.output / (a.image.name + '.parts.json')
        with path.open('x') as stream: stream.write(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    except Exception:
        # Keep partial files for diagnosis; no automatic deletion of user paths.
        raise


if __name__ == '__main__': main()
