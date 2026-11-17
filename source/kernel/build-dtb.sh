#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
src=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=$(cd -- "$src/../.." && pwd)
build=${FIREFLY_KERNEL_WORK:-"$root/work/kernel"}
mkdir -p "$build"
python3 "$src/prepare-tree.py" "$build/tree"
# The required tools are gcc (preprocessor only), dtc and fdtget.
# Alternatively run this script in the repository's builder container.
dts_dir="$build/tree/arch/arm64/boot/dts/rockchip"
gcc -E -nostdinc -undef -D__DTS__ -x assembler-with-cpp \
    -I "$build/tree/include" -I "$dts_dir" \
    "$dts_dir/rk3399-firefly-batocera-sd.dts" > "$build/rk3399-firefly-batocera-sd.pp.dts"
dtc -I dts -O dtb -o "$build/rk3399-firefly-batocera-sd.dtb" \
    "$build/rk3399-firefly-batocera-sd.pp.dts"
dtc -I dtb -O dts -o "$build/rk3399-firefly-batocera-sd.roundtrip.dts" \
    "$build/rk3399-firefly-batocera-sd.dtb"
sha256sum "$build/rk3399-firefly-batocera-sd.dtb"
