#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check the complete extracted-tree delta against the reviewed port manifest."""
import argparse
import json
from pathlib import Path
import stat


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('before', type=Path)
    p.add_argument('after', type=Path)
    p.add_argument('provenance', type=Path)
    p.add_argument('report', type=Path)
    a = p.parse_args()
    old = json.loads(a.before.read_text())['files']
    new = json.loads(a.after.read_text())['files']
    planned = json.loads(a.provenance.read_text())
    changes = {x['path']: x for x in planned['files']}
    module_prefix = 'lib/modules/'
    old_modules = {x['path'] for x in planned['donor_modules']}
    new_modules = {x['path'] for x in planned['bsp_modules']}
    assert {p for p in old if p.startswith(module_prefix)} == old_modules
    assert {p for p in new if p.startswith(module_prefix)} == new_modules
    expected_old = {p for p, x in changes.items() if x['before'] is not None}
    expected_new = {p for p, x in changes.items() if x['after'] is not None}
    additions, deletions = set(new) - set(old), set(old) - set(new)
    added_parents = {parent.as_posix() for name in expected_new
                     for parent in Path(name).parents if parent != Path('.')}
    assert additions <= (expected_new - expected_old) | new_modules | added_parents, sorted(additions)
    assert deletions <= (expected_old - expected_new) | old_modules, sorted(deletions)
    unchanged = 0
    actual_changed = []
    for name in set(old) & set(new):
        left, right = old[name], new[name]
        # Directory mtimes change naturally when replacing their children.
        left, right = dict(left), dict(right)
        if stat.S_ISDIR(left['type']) and stat.S_ISDIR(right['type']):
            left.pop('mtime', None)
            right.pop('mtime', None)
        if name in changes or name == 'lib/modules' or name.startswith(module_prefix):
            continue
        assert left == right, (name, left, right)
        unchanged += 'sha256' in left
    for name, change in changes.items():
        after = change['after']
        if after is None:
            assert name not in new
        else:
            actual = new[name]
            if after['type'] == 'file':
                assert actual['sha256'] == after['sha256'] and actual['bytes'] == after['bytes'], name
                assert actual['mode'] == int(after['mode'], 8) and actual['uid'] == actual['gid'] == 0, name
            elif after['type'] == 'symlink':
                assert actual['target'] == after['target'], name
            else:
                raise ValueError('Unsupported planned file type: ' + name)
        actual_changed.append(name)
    for item in planned['bsp_modules']:
        actual = new[item['path']]
        if item['type'] == 'file':
            assert actual['sha256'] == item['sha256'] and actual['bytes'] == item['bytes'], item['path']
            assert actual['mode'] == int(item['mode'], 8), item['path']
        elif item['type'] == 'symlink':
            assert actual['target'] == item['target'], item['path']
        assert actual['uid'] == actual['gid'] == 0, item['path']
    report = {'result': 'PASS', 'original_paths': len(old), 'final_paths': len(new),
              'unchanged_regular_files': unchanged, 'planned_files_checked': actual_changed,
              'added_paths': sorted(additions), 'removed_paths': sorted(deletions),
              'matching_bsp_module_paths': len(new_modules)}
    a.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if not isinstance(v, list)}, indent=2))


if __name__ == '__main__':
    main()
