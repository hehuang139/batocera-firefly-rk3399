#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Create the validated image manifest consumed by the onboard installer."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import stat

IMAGE_BYTES = 4580179968


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(8388608),b''):h.update(b)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('image',type=Path)
    p.add_argument('output',type=Path)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink():raise ValueError('Output already exists')
    compressed=Path(str(a.image)+'.gz')
    sidecar=a.image.with_suffix('.manifest.json')
    for f in [a.image,compressed,sidecar]:
        if f.is_symlink() or not stat.S_ISREG(f.stat().st_mode):raise ValueError('Input must be a regular file')
    expected=json.loads(sidecar.read_text())
    if (a.image.suffix!='.img' or expected.get('mode')!='emmc' or expected.get('board')!='firefly-rk3399'
            or expected.get('image')!=a.image.name or expected.get('bytes')!=IMAGE_BYTES
            or expected.get('root_device')!='/dev/mmcblk2p1' or a.image.stat().st_size!=IMAGE_BYTES):
        raise ValueError('Expected a matching Firefly eMMC image and metadata')
    if not re.fullmatch(r'[0-9a-f]{64}',expected.get('sha256','')):raise ValueError('Invalid raw image hash')
    raw=sha(a.image)
    if raw!=expected['sha256']:raise ValueError('Raw image hash mismatch')
    with gzip.open(compressed,'rb') as f:
        h=hashlib.sha256();size=0
        for b in iter(lambda:f.read(8388608),b''):h.update(b);size+=len(b)
    if h.hexdigest()!=raw or size!=IMAGE_BYTES:raise ValueError('Gzip does not match raw image')
    result={'board':'firefly-rk3399','medium':'emmc',
            'image':{'name':a.image.name,'bytes':size,'sha256':raw},
            'compressed':{'name':compressed.name,'bytes':compressed.stat().st_size,'sha256':sha(compressed)}}
    with a.output.open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
