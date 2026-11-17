#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$root"
image=${FIREFLY_BUILD_IMAGE:-firefly-rk3399-fullbuilder:20261108}
sd_gz=${1:?Usage: source/emmc/rebuild.sh /absolute/verified-SD.img.gz /absolute/new-output-directory}
out=${2:?A new output directory inside this project is required}
[[ ! -L "$sd_gz" && ! -L "$out" ]]
sd_gz=$(realpath "$sd_gz")
out=$(realpath -m "$out")
case "$sd_gz" in "$root"/*) ;; *) echo 'Place the verified SD image in the project.' >&2; exit 1;; esac
case "$out" in "$root"/*) ;; *) echo 'Output directory must be in the project.' >&2; exit 1;; esac
[[ ! -e "$out" ]]
[[ "$out" != *$'\n'* && "$out" != *$'\r'* ]]
# Validate the pinned input before building or creating an output directory.
python3 - "$sd_gz" <<'PY_INPUT'
import hashlib,json,pathlib,stat,sys
path=pathlib.Path(sys.argv[1])
if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
    raise SystemExit('The SD input must be a regular compressed image file')
expected=json.loads(pathlib.Path('source/emmc/inputs.json').read_text())['sd_compressed']
if path.stat().st_size!=expected['bytes']:
    raise SystemExit('SD image size does not match the fixed input')
h=hashlib.sha256()
with path.open('rb') as stream:
    for block in iter(lambda:stream.read(8388608),b''):h.update(block)
if h.hexdigest()!=expected['sha256']:
    raise SystemExit('SD image checksum does not match the fixed input')
PY_INPUT
mkdir -p "$(dirname "$out")" source/emmc/boot-assets
mkdir "$out"
mkdir "$out/validation"
base=${sd_gz#"$root"/}
relative=${out#"$root"/}
# Boot/kernel scripts use fixed source tarballs and the original TF DTS inputs.
FIREFLY_BOOT_BUILD_IMAGE="$image" bash source/emmc/boot/rebuild-boot.sh
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$root:/project" -w /project "$image" \
  bash source/emmc/kernel/build-dtb.sh
cp work/emmc/boot/assets/idbloader.img work/emmc/boot/assets/u-boot.itb source/emmc/boot-assets/
cp work/emmc/kernel/rk3399-firefly-batocera-emmc.dtb source/emmc/boot-assets/
# Installer retains the previously verified TF boot binaries bundled in source/boot-assets.
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$root:/project" -w /project "$image" \
  python3 source/emmc/make-image.py emmc "$base" "$relative/batocera40-firefly-rk3399-emmc-test1.img"
gzip -1 -n -k "$out/batocera40-firefly-rk3399-emmc-test1.img"
python3 source/emmc/release-manifest.py "$out/batocera40-firefly-rk3399-emmc-test1.img" "$out/manifest.json"
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$root:/project" -w /project "$image" \
  python3 source/emmc/make-image.py installer "$base" "$relative/batocera40-firefly-rk3399-emmc-installer-tf-test1.img" \
  --payload "$relative/batocera40-firefly-rk3399-emmc-test1.img.gz" --payload-manifest "$relative/manifest.json"
gzip -1 -n -k "$out/batocera40-firefly-rk3399-emmc-installer-tf-test1.img"
# The verifier independently checks these published hashes against each image.
python3 - "$out" <<'PY_SUMS'
import hashlib,pathlib,sys
out=pathlib.Path(sys.argv[1])
names=['batocera40-firefly-rk3399-emmc-test1.img',
       'batocera40-firefly-rk3399-emmc-test1.img.gz',
       'batocera40-firefly-rk3399-emmc-installer-tf-test1.img',
       'batocera40-firefly-rk3399-emmc-installer-tf-test1.img.gz',
       'manifest.json']
lines=[]
for name in names:
    h=hashlib.sha256()
    with (out/name).open('rb') as stream:
        for block in iter(lambda:stream.read(8388608),b''):h.update(block)
    lines.append(h.hexdigest()+'  '+name)
with (out/'SHA256SUMS').open('x') as stream:stream.write('\n'.join(lines)+'\n')
PY_SUMS
for mode in emmc installer; do
  if [[ "$mode" == emmc ]]; then
    name=batocera40-firefly-rk3399-emmc-test1.img
  else
    name=batocera40-firefly-rk3399-emmc-installer-tf-test1.img
  fi
  docker run --rm --network none --user "$(id -u):$(id -g)" -v "$root:/project" -w /project "$image" \
    python3 source/emmc/verify-image.py --mode "$mode" --image "$relative/$name" \
    --report "$relative/validation/$mode-image.json" --scratch "$relative/validation/scratch"
done
printf 'Images created and verified in %s\n' "$out"
