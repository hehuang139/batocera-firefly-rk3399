#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The complete, reviewed contents of the Select hotkey saved overlay."""
import hashlib
from pathlib import Path
import stat

FILE_MODES = {
    'etc/init.d/S30selecthotkey': 0o755,
    'usr/bin/firefly-select-hotkey': 0o755,
    'usr/share/batocera/datainit/system/configs/emulationstation/es_input.cfg': 0o644,
}


def inspect_tree(tree):
    if any(path.is_symlink() for path in (tree, *tree.parents)):
        raise ValueError('Overlay tree and its ancestors must not be symlinks')
    expected_dirs = {parent.as_posix() for name in FILE_MODES
                     for parent in Path(name).parents if parent != Path('.')}
    files, directories = [], [{'path': '/', 'mode': '0755'}]
    for path in sorted(tree.rglob('*')):
        relative = path.relative_to(tree).as_posix()
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode) and relative in expected_dirs:
            directories.append({'path': relative, 'mode': '0755'})
        elif stat.S_ISREG(mode) and relative in FILE_MODES:
            if stat.S_IMODE(mode) != FILE_MODES[relative]:
                raise ValueError('Unexpected file permissions: ' + relative)
            files.append({'path': relative, 'bytes': path.stat().st_size,
                          'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                          'mode': f'{FILE_MODES[relative]:04o}'})
        else:
            raise ValueError('Unexpected overlay entry: ' + relative)
    if {entry['path'] for entry in files} != set(FILE_MODES):
        raise ValueError('Missing Select hotkey overlay files')
    return files, directories
