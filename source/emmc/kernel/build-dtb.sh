#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
src=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=$(cd -- "$src/../../.." && pwd)
build=${FIREFLY_EMMC_KERNEL_WORK:-"$root/work/emmc/kernel"}
mkdir -p "$build"
python3 - "$root" <<'PY'
import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1])
m=json.loads((root/'source/emmc/kernel/inputs.json').read_text())
for relative,expected in m['sha256'].items():
    actual=hashlib.sha256((root/relative).read_bytes()).hexdigest()
    assert actual==expected, (relative,actual,expected)
PY
python3 "$root/source/kernel/prepare-tree.py" "$build/tree"
dts_dir="$build/tree/arch/arm64/boot/dts/rockchip"
cp "$src/rk3399-firefly-batocera-emmc.dts" "$dts_dir/"
for name in rk3399-firefly-batocera-sd rk3399-firefly-batocera-emmc; do
  gcc -E -nostdinc -undef -D__DTS__ -x assembler-with-cpp \
    -I "$build/tree/include" -I "$dts_dir" \
    "$dts_dir/$name.dts" > "$build/$name.pp.dts"
  dtc -I dts -O dtb -o "$build/$name.dtb" "$build/$name.pp.dts"
done
dtc -I dtb -O dts -o "$build/rk3399-firefly-batocera-emmc.roundtrip.dts" \
  "$build/rk3399-firefly-batocera-emmc.dtb"
python3 "$src/validate-dtb.py" "$build"
sha256sum "$build/rk3399-firefly-batocera-emmc.dtb"
