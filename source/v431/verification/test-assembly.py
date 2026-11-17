#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Small, real-file checks of assembly protection and inventory comparison."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
SOURCES = ROOT / 'source/v431'
checks = []


def call(name, command, succeeds):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    ok = (result.returncode == 0) == succeeds
    checks.append({'name': name, 'pass': ok, 'exit_code': result.returncode,
                   'output': result.stdout[-1200:]})
    return ok


def write_json(path, data):
    path.write_text(json.dumps(data))


def main(report_path):
    with tempfile.TemporaryDirectory(prefix='v431-assembly-tests-') as tmp:
        tmp = Path(tmp)
        metadata = {'mode': 0o644, 'type': stat.S_IFREG, 'uid': 0, 'gid': 0, 'mtime': 1000000000,
                    'bytes': 3, 'sha256': hashlib.sha256(b'abc').hexdigest()}
        directory = {'mode': 0o755, 'type': stat.S_IFDIR, 'uid': 0, 'gid': 0, 'mtime': 1000000000}
        old = {'files': {'.': directory, 'lib': directory, 'lib/modules': directory,
                          'lib/modules/6.6.56': directory, 'usr': directory, 'usr/unchanged': metadata}}
        new = {'files': {'.': directory, 'lib': directory, 'lib/modules': directory,
                          'lib/modules/6.6.27': directory, 'usr': directory, 'usr/unchanged': metadata}}
        provenance = {'files': [],
                      'donor_modules': [{'path': 'lib/modules/6.6.56', 'type': 'directory', 'mode': '0755'}],
                      'bsp_modules': [{'path': 'lib/modules/6.6.27', 'type': 'directory', 'mode': '0755'}]}
        before, after, plan = [tmp / name for name in ['before.json', 'after.json', 'plan.json']]
        write_json(before, old); write_json(plan, provenance)
        def compare(name, value, succeeds):
            write_json(after, value)
            call(name, [sys.executable, str(SOURCES / 'compare-inventories.py'), str(before), str(after),
                        str(plan), str(tmp / 'comparison.json')], succeeds)
        compare('valid-pinned-tree-transition', new, True)
        changed = copy.deepcopy(new);changed['files']['usr/unchanged']['mtime'] += 1000000000
        compare('unchanged-regular-file-mtime-rejected', changed, False)
        changed = copy.deepcopy(new);changed['files']['usr']['mtime'] += 1000000000
        compare('directory-mtime-change-allowed', changed, True)
        changed = copy.deepcopy(new);changed['files']['usr/unchanged']['sha256'] = '0' * 64
        compare('unexpected-content-change-rejected', changed, False)
        changed = copy.deepcopy(new);changed['files']['usr/extra'] = metadata
        compare('unplanned-file-addition-rejected', changed, False)
        changed = copy.deepcopy(new);changed['files']['lib/modules/6.6.56'] = directory
        compare('donor-module-tree-leftover-rejected', changed, False)
        existing = tmp / 'batocera431-firefly-rk3399-emmc-test1.img'
        existing.write_bytes(b'keep')
        call('assembler-existing-image-rejected', [sys.executable, str(SOURCES / 'make-image.py'), 'emmc',
                                                  str(tmp / 'missing.sqfs'), str(existing)], False)
        checks.append({'name': 'existing-image-content-preserved', 'pass': existing.read_bytes() == b'keep'})
        link = tmp / 'batocera431-firefly-rk3399-emmc-installer-tf-test1.img'
        link.symlink_to(tmp / 'absent-target')
        call('assembler-dangling-output-symlink-rejected', [sys.executable, str(SOURCES / 'make-image.py'), 'installer',
                                                          str(tmp / 'missing.sqfs'), str(link)], False)
        invalid_name = tmp / 'wrong-name.img'
        call('assembler-wrong-release-name-rejected', [sys.executable, str(SOURCES / 'make-image.py'), 'emmc',
                                                      str(tmp / 'missing.sqfs'), str(invalid_name)], False)
        check_scratch = tmp / 'packed-scratch';check_scratch.mkdir()
        (check_scratch / 'packed-rootfs').symlink_to(tmp / 'dangling-root')
        call('packed-check-dangling-root-rejected', [sys.executable, str(SOURCES / 'verify-packed-rootfs.py'),
                                                   str(tmp / 'missing.sqfs'), str(before), str(check_scratch), str(tmp / 'packed.json')], False)
    report = {'result': 'PASS' if all(x['pass'] for x in checks) else 'FAIL', 'count': len(checks),
              'passed': sum(x['pass'] for x in checks), 'checks': checks,
              'source_sha256': {name: hashlib.sha256((SOURCES / name).read_bytes()).hexdigest()
                                for name in ['make-image.py', 'compare-inventories.py', 'verify-packed-rootfs.py']},
              'scope': 'Ordinary temporary files and real Python entry points; no large image or block device.'}
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'result': report['result'], 'passed': report['passed'], 'count': len(checks)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, required=True)
    main(parser.parse_args().report)
