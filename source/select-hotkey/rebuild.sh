#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$root"
builder=${FIREFLY_BUILD_IMAGE:-firefly-rk3399-fullbuilder:20261108}
input=${1:?Usage: rebuild.sh /absolute/verified-SD.img.gz /absolute/new-output-directory}
output=${2:?A new output directory inside this project is required}
[[ ! -L "$input" && ! -L "$output" && ! -e "$output" ]]
input=$(realpath "$input")
output=$(realpath -m "$output")
case "$input" in "$root"/*) ;; *) echo 'Input must be inside this project.' >&2; exit 1;; esac
case "$output" in "$root"/*) ;; *) echo 'Output must be inside this project.' >&2; exit 1;; esac
[[ "$output" != *$'\n'* && "$output" != *$'\r'* ]]
base=${input#"$root"/}
out=${output#"$root"/}
python3 - "$input" <<'PY_INPUT'
import hashlib,json,pathlib,stat,sys
path=pathlib.Path(sys.argv[1])
expected=json.loads(pathlib.Path('source/emmc/inputs.json').read_text())['sd_compressed']
if not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size!=expected['bytes']:
    raise SystemExit('Expected the fixed Firefly SD release as an ordinary file')
h=hashlib.sha256()
with path.open('rb') as stream:
    for chunk in iter(lambda:stream.read(8388608),b''): h.update(chunk)
if h.hexdigest()!=expected['sha256']:
    raise SystemExit('SD release SHA256 mismatch')
PY_INPUT
mkdir -p "$(dirname -- "$output")"
mkdir "$output"
mkdir "$output/validation" "$output/overlay-build" "$output/baseline-logs"
run_builder() {
    docker run --rm --network none --user "$(id -u):$(id -g)" \
        -v "$root:/project" -w /project "$builder" "$@"
}
# Build the pinned boot components needed by the independent image verifier.
# Source tarballs, configurations and DTS inputs are included in the package.
FIREFLY_BOOT_BUILD_IMAGE="$builder" bash source/boot/rebuild-boot.sh
FIREFLY_BOOT_BUILD_IMAGE="$builder" bash source/emmc/boot/rebuild-boot.sh
run_builder bash source/emmc/kernel/build-dtb.sh
# Assembly and verification must refer to the same freshly built components.
mkdir -p source/boot-assets source/emmc/boot-assets source/select-hotkey/assets
cp work/boot/assets/idbloader.img work/boot/assets/u-boot.itb source/boot-assets/
cp work/emmc/boot/assets/idbloader.img work/emmc/boot/assets/u-boot.itb source/emmc/boot-assets/
cp work/emmc/kernel/rk3399-firefly-batocera-emmc.dtb source/emmc/boot-assets/
python3 source/select-hotkey/build-config.py \
    --config-source source/select-hotkey/provenance/es_input.cfg
python3 source/select-hotkey/validate.py
cp source/select-hotkey/validation.json "$output/validation/hotkey.json"
run_builder python3 source/select-hotkey/build-overlay.py "$out/overlay-build/overlay" \
    --manifest "$out/overlay-build/overlay-manifest.json"
cp "$output/overlay-build/overlay" "$output/overlay-build/overlay-manifest.json" source/select-hotkey/assets/
emmc=batocera40-firefly-rk3399-emmc-test2.img
installer=batocera40-firefly-rk3399-emmc-installer-tf-test2.img
run_builder python3 source/select-hotkey/make-image.py emmc "$base" "$out/$emmc"
gzip -1 -n -k "$output/$emmc"
python3 source/emmc/release-manifest.py "$output/$emmc" "$output/manifest.json"
run_builder python3 source/select-hotkey/make-image.py installer "$base" "$out/$installer" \
    --payload "$out/$emmc.gz" --payload-manifest "$out/manifest.json"
gzip -1 -n -k "$output/$installer"
python3 - "$output" <<'PY'
import hashlib,pathlib,sys
out=pathlib.Path(sys.argv[1])
lines=[]
for path in sorted(out.iterdir()):
    if not path.is_file(): continue
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(8388608),b''): h.update(block)
    lines.append(h.hexdigest()+'  '+path.name)
(out/'SHA256SUMS').write_text('\n'.join(lines)+'\n')
PY
for mode in emmc installer; do
    target=$emmc
    [[ "$mode" != installer ]] || target=$installer
    docker run --rm --network none --user "$(id -u):$(id -g)" \
        -v "$root:/project" -v "$output/baseline-logs:/project/work/emmc/verify-image" \
        -w /project "$builder" python3 source/select-hotkey/verify-image.py \
        --mode "$mode" --image "$out/$target" --scratch "$out/verify" \
        --report "$out/validation/image-$mode.json"
done
cp source/boot/manifest.json "$output/validation/boot-sd.json"
cp source/emmc/boot/manifest.json "$output/validation/boot-emmc.json"
cp source/select-hotkey/docs/*.md "$output/"
printf 'Select hotkey images built and verified in %s\n' "$output"
