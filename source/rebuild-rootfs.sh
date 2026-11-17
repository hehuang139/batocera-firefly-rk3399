#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Invoked by rebuild-image.sh inside the build container.
set -euo pipefail
base_image=$1
output_image=$2
rebuild_dir=$3
python3 - "$base_image" "$rebuild_dir/base.img" <<'PY'
import gzip, hashlib, json, pathlib, shutil, sys
base, target = map(pathlib.Path, sys.argv[1:])
manifest = json.loads(pathlib.Path('source/base-manifest.json').read_text())
h = hashlib.sha256()
with base.open('rb') as f:
    for b in iter(lambda: f.read(8388608), b''): h.update(b)
assert h.hexdigest() == manifest['sha256'], 'Base checksum mismatch'
with gzip.open(base, 'rb') as src, target.open('xb') as dst:
    shutil.copyfileobj(src, dst, 8388608)
assert target.stat().st_size == 4580179968
PY
mcopy -i "$rebuild_dir/base.img@@16777216" ::/boot/batocera "$rebuild_dir/base.squashfs"
# The independent disk verifier compares these original kernel/initrd bytes.
mkdir -p work/base-boot/boot
mcopy -o -i "$rebuild_dir/base.img@@16777216" ::/boot/linux work/base-boot/boot/linux
mcopy -o -i "$rebuild_dir/base.img@@16777216" ::/boot/initrd.lz4 work/base-boot/boot/initrd.lz4
unsquashfs -processors 4 -no-progress -d "$rebuild_dir/rootfs" "$rebuild_dir/base.squashfs"
python3 source/rootfs/apply.py "$rebuild_dir/rootfs" --report "$rebuild_dir/adaptation.json"
python3 source/rootfs/validate.py "$rebuild_dir/rootfs" --report "$rebuild_dir/rootfs-behavior.json"
mksquashfs "$rebuild_dir/rootfs" "$rebuild_dir/firefly.squashfs" \
  -noappend -no-duplicates -no-sparse -comp zstd -Xcompression-level 15 -b 131072 \
  -processors 4 -no-progress -mkfs-time 1794096000
python3 source/verify-rootfs.py "$rebuild_dir/base.squashfs" "$rebuild_dir/firefly.squashfs" \
  "$rebuild_dir/adaptation.json" "$rebuild_dir/rootfs-validation.json"
python3 source/make-image.py "$base_image" "$rebuild_dir/firefly.squashfs" "$output_image"
chown "$RELEASE_UID:$RELEASE_GID" "$output_image" "${output_image%.img}.manifest.json" \
  "$rebuild_dir/adaptation.json" "$rebuild_dir/rootfs-behavior.json" "$rebuild_dir/rootfs-validation.json"
