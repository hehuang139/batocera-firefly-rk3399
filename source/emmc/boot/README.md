# Firefly RK3399 eMMC 引导程序

原版 Firefly-RK3399 DDR3 开发板的 eMMC 用户区引导，使用 U-Boot v2024.01、ARM Trusted Firmware v2.10 和 U-Boot 自编 DDR3 TPL。源码压缩包与哈希复用项目 `source/boot/` 的固定输入；本目录及 `work/emmc/boot/` 独立于已交付 TF 版。

## 引导策略

- `u-boot,spl-boot-order = &sdhci`，SPL 只从 eMMC 控制器 `0xfe330000` 读取 FIT。
- U-Boot 默认 `boot_targets=mmc1 mmc0`，插入 TF 救援/安装卡时优先读取其 extlinux；无可启动 TF 时从 eMMC 读取系统。SPL 自身仍只从 eMMC 读取本 U-Boot。
- 环境为 `ENV_IS_NOWHERE`，不读取或写入旧 MMC 环境。
- DDR 保持原版 Firefly 的 DDR3 800 MHz（DDR3-1600），没有使用 RockPro64 的 LPDDR4 初始化代码。
- U-Boot 阶段 eMMC 限为 52 MHz，删除 HS400/增强选通属性，HS200/HS400 构建选项关闭；Linux 阶段的 eMMC 模式由独立 Linux 设备树决定。
- 不在 U-Boot 初始化显示，保留 UART2 1,500,000 波特率。Linux 接管 HDMI。

## 设备编号

U-Boot `arch/arm/dts/rk3399-u-boot.dtsi` 在 `/aliases` 覆盖为 `mmc0=&sdhci`、`mmc1=&sdmmc`。Linux `rk3399-firefly.dts` 保留 `mmc0=&sdio0`、`mmc1=&sdmmc`、`mmc2=&sdhci`。因此本启动器的 eMMC 是 **U-Boot mmc0**；Linux eMMC 根分区为 **`/dev/mmcblk2p1`**。不要把 U-Boot 编号直接套用到 Linux。

烧录完成后断电拔 TF 卡，再用独立电源启动 eMMC 系统。需要恢复或重装时，可断电插入本项目 TF 安装卡后再启动；优先进入安装卡不代表自动写 eMMC，仍需明确执行安装命令。没有 TF 卡也可独立启动 eMMC。芯片 ROM 及此前烧写到 SPI 的固件仍可能影响最初启动选择；这不通过改写 TF 卡来解决。

## 重建

在项目根目录执行：

```sh
bash source/emmc/boot/rebuild-boot.sh
```

默认工具容器：`firefly-rk3399-fullbuilder:20261108`，由项目 `source/Dockerfile` 构建；可用 `FIREFLY_BOOT_BUILD_IMAGE` 指定替代。无网络、无设备映射，仅项目目录挂入容器。

生成 `work/emmc/boot/assets/`、`source/emmc/boot/built.config` 和 `source/emmc/boot/manifest.json`。构建结束自动执行 `validate-boot.py`，检查实际 TPL/SPL/FIT/ELF、DDR 参数、eMMC 别名、启动顺序与速度限制。

## 放入整盘镜像

| 文件 | 整盘绝对偏移 |
| --- | --- |
| `idbloader.img` | 32 KiB / LBA 64 |
| `u-boot.itb` | 8 MiB / LBA 16384 |

也可将 `u-boot-rockchip.bin` 放在 32 KiB；它自身已包含两个资产及间隙。不要同时叠加不同构建的资产。`idbloader.img` 是盘上启动映像，并非 `rkdeveloptool db` 使用的 USB RAM Loader。

源码中的许可证保持上游文件说明；新构建/验证脚本使用 MIT。
