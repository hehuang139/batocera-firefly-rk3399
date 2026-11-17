#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Package and read back the exact source files and release validation records."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import stat
import tarfile

ROOT = Path(__file__).resolve().parent.parent
PREFIX = 'firefly-rk3399-batocera/'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--validation-dir', type=Path, default=ROOT/'outputs/validation')
    a = p.parse_args()
    if a.output.exists() or a.output.is_symlink():
        raise ValueError('Refusing to overwrite an existing archive')
    files = [(ROOT/'README.md', 'README.md')]
    for subtree, archive_root in [(ROOT/'source', 'source'), (a.validation_dir.resolve(), 'validation')]:
        for path in sorted(subtree.rglob('*')):
            if '__pycache__' in path.parts or path.suffix == '.pyc':
                continue
            if path.is_file() or path.is_symlink():
                files.append((path, archive_root+'/'+path.relative_to(subtree).as_posix()))
    manifest = []
    with tarfile.open(a.output, 'x:gz', compresslevel=6) as tar:
        for path, relative in files:
            if path.is_symlink():
                raise ValueError('Source symlink needs explicit review: '+str(path))
            data = path.read_bytes()
            entry = {'path':relative,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
            manifest.append(entry)
            info = tarfile.TarInfo(PREFIX+relative)
            info.size = len(data)
            info.mode = stat.S_IMODE(path.stat().st_mode)
            info.mtime = 1794096000
            tar.addfile(info, io.BytesIO(data))
        data = (json.dumps({'files':manifest},indent=2)+'\n').encode()
        info = tarfile.TarInfo(PREFIX+'SOURCE-MANIFEST.json')
        info.size,info.mode,info.mtime = len(data),0o644,1794096000
        tar.addfile(info,io.BytesIO(data))
    with tarfile.open(a.output, 'r:gz') as tar:
        actual = {member.name for member in tar.getmembers()}
        assert actual == {PREFIX+x['path'] for x in manifest} | {PREFIX+'SOURCE-MANIFEST.json'}
        for item in manifest:
            data = tar.extractfile(PREFIX+item['path']).read()
            assert len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256']
    report = {'result':'PASS','archive':a.output.name,'files_checked':len(manifest),
              'bytes':a.output.stat().st_size,'sha256':hashlib.sha256(a.output.read_bytes()).hexdigest()}
    a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
