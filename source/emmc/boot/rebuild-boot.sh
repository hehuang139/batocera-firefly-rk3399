#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
if [[ ${1:-} != --inside ]]; then
    build_image=${FIREFLY_BOOT_BUILD_IMAGE:-firefly-rk3399-fullbuilder:20261108}
    exec docker run --rm --network none \
        --user "$(id -u):$(id -g)" \
        --volume "$project_dir:/project" --workdir /project \
        --env "BOOT_BUILD_JOBS=${BOOT_BUILD_JOBS:-4}" \
        --env SOURCE_DATE_EPOCH=1704700800 --env TZ=UTC \
        --env KBUILD_BUILD_USER=firefly --env KBUILD_BUILD_HOST=buildhost \
        --env PYTHONDONTWRITEBYTECODE=1 --entrypoint /bin/bash \
        "$build_image" /project/source/emmc/boot/rebuild-boot.sh --inside
fi

cd "$project_dir"
mkdir -p work/emmc/boot/src work/emmc/boot/assets logs
exec > >(tee logs/emmc-boot-build.log) 2>&1
printf 'Building Firefly RK3399 DDR3 eMMC boot components\n'
(cd source/boot && sha256sum -c SHA256SUMS.sources)
tar -xzf source/boot/u-boot-v2024.01.tar.gz -C work/emmc/boot/src
tar -xzf source/boot/arm-trusted-firmware-v2.10.tar.gz -C work/emmc/boot/src

python3 - <<'PY'
from pathlib import Path
root = Path('work/emmc/boot/src/u-boot-2024.01')
p = root / 'arch/arm/dts/rk3399-firefly-u-boot.dtsi'
s = p.read_text()
before = 'u-boot,spl-boot-order = "same-as-spl", &sdhci, &sdmmc;'
assert s.count(before) == 1
p.write_text(s.replace(before, 'u-boot,spl-boot-order = &sdhci;'))
p.write_text(p.read_text() + '''
/* eMMC first-boot policy: avoid HS400 and cap this boot stage at 52 MHz. */
&sdhci {
    /delete-property/ mmc-hs400-1_8v;
    /delete-property/ mmc-hs400-enhanced-strobe;
    max-frequency = <52000000>;
};
''')
p = root / 'include/configs/rockchip-common.h'
s = p.read_text()
before = '#define BOOT_TARGETS\t"mmc1 mmc0 nvme scsi usb pxe dhcp spi"'
assert s.count(before) == 1
p.write_text(s.replace(before, '#define BOOT_TARGETS\t"mmc1 mmc0"'))
p = Path('work/emmc/boot/src/arm-trusted-firmware-2.10/plat/rockchip/rk3399/drivers/m0/Makefile')
s = p.read_text()
# Ubuntu's arm-linux-gnueabihf compiler defaults to PIE. Cortex-M0 firmware
# uses a bare-metal fixed-address linker script and must be non-PIE.
before = 'CFLAGS\t\t\t:= -ffunction-sections'
assert s.count(before) == 1
s = s.replace(before, 'CFLAGS\t\t\t:= -fno-pie -ffunction-sections')
before = 'LDFLAGS\t\t\t:= -Wl,--gc-sections'
assert s.count(before) == 1
p.write_text(s.replace(before, 'LDFLAGS\t\t\t:= -no-pie -Wl,--gc-sections'))
PY

build_jobs=${BOOT_BUILD_JOBS:-4}
make -C work/emmc/boot/src/arm-trusted-firmware-2.10 PLAT=rk3399 \
    BUILD_BASE="$project_dir/work/emmc/boot/tfa" clean
make -C work/emmc/boot/src/arm-trusted-firmware-2.10 -j"$build_jobs" \
    PLAT=rk3399 CROSS_COMPILE=aarch64-linux-gnu- \
    M0_CROSS_COMPILE=arm-linux-gnueabihf- \
    BUILD_BASE="$project_dir/work/emmc/boot/tfa" bl31

uboot_source="$project_dir/work/emmc/boot/src/u-boot-2024.01"
uboot_output="$project_dir/work/emmc/boot/uboot"
make -C "$uboot_source" O="$uboot_output" CROSS_COMPILE=aarch64-linux-gnu- firefly-rk3399_defconfig
"$uboot_source/scripts/kconfig/merge_config.sh" -m -O "$uboot_output" \
    "$uboot_output/.config" "$project_dir/source/emmc/boot/firefly-emmc.config"
make -C "$uboot_source" O="$uboot_output" CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
make -C "$uboot_source" O="$uboot_output" CROSS_COMPILE=aarch64-linux-gnu- \
    BL31="$project_dir/work/emmc/boot/tfa/rk3399/release/bl31/bl31.elf" -j"$build_jobs"

cp "$uboot_output/idbloader.img" "$uboot_output/u-boot.itb" \
   "$uboot_output/u-boot-rockchip.bin" "$uboot_output/u-boot.dtb" work/emmc/boot/assets/
cp "$uboot_output/.config" source/emmc/boot/built.config
cp work/emmc/boot/tfa/rk3399/release/bl31/bl31.elf work/emmc/boot/assets/
"$uboot_output/tools/dumpimage" -l "$uboot_output/u-boot.itb" > work/emmc/boot/fit-list.txt
python3 source/emmc/boot/validate-boot.py
