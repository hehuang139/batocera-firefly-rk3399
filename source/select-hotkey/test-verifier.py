#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise overlay validation with clean and deliberately damaged fixtures."""
import argparse
import importlib.util
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    source = HERE / 'verify-image.py'
    spec = importlib.util.spec_from_file_location('verify_test2', source)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    records = []
    with tempfile.TemporaryDirectory(prefix='ff-overlay-validation-') as temporary:
        work = Path(temporary)
        tree = work / 'tree'
        tree.mkdir()
        files, directories = [], {'/'}
        for name, mode in verifier.EXPECTED_FILES.items():
            path = tree / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture ' + name + '\n')
            path.chmod(mode)
            files.append({'path': name, 'bytes': path.stat().st_size,
                          'sha256': verifier.digest(path), 'mode': f'{mode:04o}'})
            directories.update(str(parent) for parent in PurePosixPath(name).parents
                               if str(parent) != '.')
        image = work / 'overlay'
        with image.open('xb') as stream:
            stream.truncate(verifier.OVERLAY_BYTES)
        subprocess.run(['mke2fs', '-q', '-F', '-t', 'ext4', '-b', '1024',
                        '-O', '^has_journal', '-E', 'root_owner=0:0',
                        '-d', str(tree), str(image)], check=True)
        manifest = {'image': {'name': 'overlay', 'bytes': verifier.OVERLAY_BYTES},
                    'files': files,
                    'directories': [{'path': path, 'mode': '0755'} for path in sorted(directories)]}
        commands = ['rmdir /lost+found']
        for item in manifest['directories'] + files:
            name = '/' + item['path'].lstrip('/')
            kind = stat.S_IFDIR if item in manifest['directories'] else stat.S_IFREG
            mode = kind | int(item['mode'], 8)
            commands.extend([f'set_inode_field {name} uid 0',
                             f'set_inode_field {name} gid 0',
                             f'set_inode_field {name} mode 0{mode:o}'])
        batch = work / 'metadata.debugfs'
        batch.write_text('\n'.join(commands) + '\n')
        subprocess.run(['debugfs', '-w', '-f', str(batch), str(image)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        def test(name, command=None, expected_failure=None):
            current = work / name
            shutil.copyfile(image, current)
            if command:
                subprocess.run(['debugfs', '-w', '-R', command, str(current)], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            metadata = json.loads(json.dumps(manifest))
            # Permit the changed outer image hash so each test exercises the
            # filesystem, inode and path checks beyond the SHA256 comparison.
            metadata['image']['sha256'] = verifier.digest(current)
            scratch = work / (name + ' scratch')
            scratch.mkdir()
            verifier.checks.clear()
            try:
                verifier.verify_overlay(current, metadata, current, scratch)
                if expected_failure:
                    raise AssertionError('Corrupt fixture was accepted: ' + name)
                records.append({'name': name, 'result': 'PASS', 'checks': len(verifier.checks)})
            except RuntimeError as error:
                if not expected_failure or not str(error).startswith(expected_failure + ':'):
                    raise
                records.append({'name': name, 'result': 'PASS',
                                'rejected_by': verifier.checks[-1]['name']})

        test('valid')
        test('dirty', 'set_super_value state 2', 'overlay-clean-no-journal')
        test('wrong-owner', 'set_inode_field /usr/bin/firefly-select-hotkey uid 1000',
             'overlay-inode:/usr/bin/firefly-select-hotkey')
        test('extra-link', 'symlink /surprise /usr/bin/firefly-select-hotkey',
             'overlay-no-extra-paths')
        test('wrong-mode', 'set_inode_field /etc/init.d/S30selecthotkey mode 0100644',
             'overlay-inode:/etc/init.d/S30selecthotkey')
    result = {'verifier_sha256': verifier.digest(source), 'result': 'PASS', 'cases': records}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
