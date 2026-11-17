#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Hash every regular file from an unsquashfs -pf export (metadata plus data)."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('export', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    records, links = {}, {}
    with a.export.open('rb') as f:
        found_data = False
        while True:
            line = f.readline()
            if not line:
                raise ValueError('Missing pseudo export data marker')
            if line == b'# START OF DATA - DO NOT MODIFY\n':
                assert f.readline() == b'#\n'
                start = f.tell()
                found_data = True
                break
            if line.startswith(b'#') or not line.strip():
                continue
            fields = shlex.split(line.decode('utf-8'))
            kind = fields[1]
            if kind == 'R':
                assert len(fields) == 8, fields
                records[fields[0]] = {'size':int(fields[6]), 'offset':int(fields[7])}
            elif kind == 'L':
                assert len(fields) == 3, fields
                links[fields[0]] = fields[2]
            elif kind not in ['D', 'S', 'B', 'C', 'I']:
                raise ValueError('Unsupported pseudo entry ' + line.decode())
        assert found_data
        payload_size = a.export.stat().st_size - start
        expected_end = 0
        for name, record in sorted(records.items(), key=lambda item:item[1]['offset']):
            assert record['offset'] == expected_end, (name, record, expected_end)
            f.seek(start + record['offset'])
            remaining, h = record['size'], hashlib.sha256()
            while remaining:
                block = f.read(min(8388608, remaining))
                assert block, (name, remaining)
                h.update(block)
                remaining -= len(block)
            expected_end += record['size']
            record['sha256'] = h.hexdigest()
            del record['offset']
        assert expected_end == payload_size, (expected_end, payload_size)
    while links:
        count = len(links)
        for name, target in list(links.items()):
            if target in records:
                records[name] = dict(records[target])
                del links[name]
        if len(links) == count:
            raise ValueError('Unresolved hard links: ' + str(links))
    a.output.write_text(json.dumps({'regular_paths':len(records), 'data_bytes':payload_size,
        'files':dict(sorted(records.items()))}, indent=2)+'\n')
    print('Hashed regular paths:', len(records), 'data bytes:', payload_size)


if __name__ == '__main__':
    main()
