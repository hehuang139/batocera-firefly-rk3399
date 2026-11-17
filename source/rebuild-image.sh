#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_dir"
base_image=${1:?Usage: source/rebuild-image.sh /absolute/base.img.gz /absolute/new-output.img}
output_image=${2:?Provide a new .img output path inside this project}
build_image=${FIREFLY_BUILD_IMAGE:-firefly-rk3399-fullbuilder:20261108}
[[ ! -L "$output_image" ]]
base_image=$(realpath "$base_image")
output_image=$(realpath -m "$output_image")
case "$base_image" in "$project_dir"/*) ;; *) echo 'Place the base image inside this project first.' >&2; exit 1;; esac
case "$output_image" in "$project_dir"/*) ;; *) echo 'Output must be inside this project.' >&2; exit 1;; esac
[[ ! -e "$output_image" && ! -L "$output_image" ]]
[[ "$output_image" == *.img ]]
for sidecar in "$output_image.gz" "${output_image%.img}.manifest.json" "${output_image%.img}.validation.json"; do
  [[ ! -e "$sidecar" && ! -L "$sidecar" ]] || { echo "Output already exists: $sidecar" >&2; exit 1; }
done
[[ "$output_image" != *$'\n'* && "$output_image" != *$'\r'* ]]
checksum_file="$(dirname "$output_image")/SHA256SUMS"
[[ ! -L "$checksum_file" && ( ! -e "$checksum_file" || -f "$checksum_file" ) ]]
mkdir -p work logs source/boot-assets "$(dirname "$output_image")"
FIREFLY_BOOT_BUILD_IMAGE="$build_image" bash source/boot/rebuild-boot.sh
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$project_dir:/project" -w /project "$build_image" \
  bash source/kernel/build-dtb.sh
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$project_dir:/project" -w /project "$build_image" \
  python3 source/kernel/validate-dtb.py
cp work/boot/assets/idbloader.img work/boot/assets/u-boot.itb source/boot-assets/
cp work/kernel/rk3399-firefly-batocera-sd.dtb source/boot-assets/
rebuild_dir=$(mktemp -d "$project_dir/work/rebuild.XXXXXX")
base_relative=${base_image#"$project_dir"/}
output_relative=${output_image#"$project_dir"/}
rebuild_relative=${rebuild_dir#"$project_dir"/}
# Root is limited to this container's project mount. It preserves the upstream
# filesystem's UIDs, modes and links; no host /dev is mounted or written.
docker run --rm --network none -v "$project_dir:/project" -w /project \
  -e RELEASE_UID="$(id -u)" -e RELEASE_GID="$(id -g)" \
  "$build_image" bash source/rebuild-rootfs.sh \
  "$base_relative" "$output_relative" "$rebuild_relative"
gzip -1 -n -k "$output_image"
docker run --rm -i --network none --user "$(id -u):$(id -g)" \
  -v "$project_dir:/project" -w /project "$build_image" \
  python3 - "$output_relative" <<'PY'
import hashlib, os, pathlib, re, sys, tempfile
image = pathlib.Path(sys.argv[1])
paths = [image, pathlib.Path(str(image) + '.gz')]
checksum_file = image.parent / 'SHA256SUMS'
if checksum_file.is_symlink():
    raise SystemExit('Refusing a symlink SHA256SUMS')
previous = checksum_file.read_text().splitlines() if checksum_file.exists() else []
names = {path.name for path in paths}
lines = []
for line in previous:
    if not line.strip():
        continue
    match = re.fullmatch(r'([0-9a-fA-F]{64}) [ *](.+)', line)
    if not match:
        raise SystemExit('Malformed existing SHA256SUMS entry')
    if match[2] not in names:
        lines.append(line)
for path in paths:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8388608), b''):
            digest.update(block)
    lines.append(f'{digest.hexdigest()}  {path.name}')
with tempfile.NamedTemporaryFile(mode='w', dir=image.parent, delete=False) as stream:
    stream.write('\n'.join(lines) + '\n')
    temporary = pathlib.Path(stream.name)
temporary.chmod(0o644)
os.replace(temporary, checksum_file)
PY
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$project_dir:/project" -w /project "$build_image" \
  python3 source/verify-image.py --image "$output_relative" \
  --report "${output_relative%.img}.validation.json"
printf 'Created %s.gz\n' "$output_image"
