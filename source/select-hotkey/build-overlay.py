#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build Batocera's saved ext4 overlay as an ordinary file, without mounting it."""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import tempfile
from spec import inspect_tree

HERE = Path(__file__).resolve().parent
SIZE = 16 * 1024 * 1024


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    for path in (args.output, args.manifest):
        if path.exists() or path.is_symlink():
            raise ValueError('Refusing to overwrite ' + str(path))
    tree = HERE / 'overlay'
    files, directories = inspect_tree(tree)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('xb') as stream:
        stream.truncate(SIZE)
    subprocess.run(['mke2fs', '-q', '-F', '-t', 'ext4', '-b', '1024',
                    '-L', 'FIREFLY_HOTKEY', '-U', 'fd1187c2-cb02-4b38-a66e-483ee3d37c43',
                    '-O', '^has_journal', '-E', 'root_owner=0:0', '-d', str(tree),
                    str(args.output)], check=True)
    commands = ['rmdir /lost+found']
    for item in directories + files:
        name = '/' + item['path'].lstrip('/')
        kind = stat.S_IFDIR if item in directories else stat.S_IFREG
        for field, value in [('uid', '0'), ('gid', '0'),
                             ('mode', f'0{kind | int(item["mode"], 8):o}')]:
            commands.append(f'set_inode_field "{name}" {field} {value}')
    with tempfile.TemporaryDirectory(dir=args.output.parent) as temporary:
        batch = Path(temporary) / 'metadata.debugfs'
        batch.write_text('\n'.join(commands) + '\n')
        subprocess.run(['debugfs', '-w', '-f', str(batch), str(args.output)],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    result = subprocess.run(['e2fsck', '-f', '-n', str(args.output)],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode:
        raise ValueError('Overlay filesystem check failed: ' + result.stdout)
    manifest = {'format': 1, 'purpose': 'Select is each gamepad hotkey',
                'image': {'name': args.output.name, 'bytes': SIZE, 'sha256': digest(args.output)},
                'uid': 0, 'gid': 0, 'files': files, 'directories': directories,
                'filesystem_check': {'result': 'PASS', 'exit_code': result.returncode,
                                     'output': result.stdout}}
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    with args.manifest.open('x') as stream:
        stream.write(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
