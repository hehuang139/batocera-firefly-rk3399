# Firefly RK3399 · Batocera 43.1

面向原版 Firefly-RK3399 DDR3。系统用户态来自官方 Batocera 43.1 ARM64 发布包，包含 43.1 的 EmulationStation、RetroArch、配置生成器、Mesa / Panfrost、Wayland / Labwc 与其他模拟器。板级部分使用本项目的 RK3399 Linux 6.6.27、完整匹配模块、Firefly 设备树和 DDR3 启动器。

本版支持 eMMC 独立启动、TF 救援和 TF 安装卡。手柄 Hotkey 使用每只手柄自己的 Select；Select + Start 退出游戏。配对或重新保存配置后自动同步，键盘和没有 Select 按钮映射的设备保留原设置。

## 来源

- Batocera 43.1 标签 `batocera-43.1`：`155c2d8d304cbb53db52e9479dcf683392821d5c`。
- 官方 ARM64 用户态：Odroid N2+ 的 `43.1 2026/06/01 19:14`，原始版本信息原样保留。官方未提供 RK3399 43.1 稳定二进制镜像；N2+ 与 RK3399 同属 ARMv8-A，并使用 Panfrost / Wayland。移植修改硬件配置与模块，保留 43.1 的程序和核心库。
- 官方发布包和校验来源记录在 `provenance/base-manifest.json`。
- RK3399 内核、模块及设备树来源和许可在上级 `source/kernel/`、`source/emmc/kernel/`；启动器在 `source/boot/`、`source/emmc/boot/`。
- 用户态每项修改、原始哈希、模块完整清单见 `rootfs/provenance.json`。

## 镜像

`batocera431-firefly-rk3399-emmc-installer-tf-test1.img.gz` 是推荐入口，写入 TF 卡，包含完整 eMMC 固件与安装程序。其启动分区为 6 GiB。

`batocera431-firefly-rk3399-emmc-test1.img.gz` 是 eMMC 用户区整盘镜像，4 GiB 启动分区，首次启动自动扩展数据分区。安装会替换旧系统与分区，按 [安装说明](docs/eMMC安装说明.md) 先备份。

准备至少 16 GB TF 卡和标称至少 8 GB eMMC。

## 构建与验证

构建脚本使用普通文件，不直接操作电脑磁盘设备。完整构建入口、固定输入和实际验证报告随发行包提供。验证包括官方基底校验、Cortex-A72 QEMU 执行、关键 ELF 依赖、全量文件内容及元数据比较、整盘启动配置和完整压缩回读。

许可证按每项上游来源保留；新增脚本使用 MIT。

系统保留官方 43.1 的双 SquashFS 布局：主系统 `boot/batocera` 与模拟器附加层 `boot/rufomaculata`，由官方 43.1 initramfs 按原顺序挂载。附加层和 initramfs 保持官方字节内容；Firefly 的内核和模块均为 6.6.27。

当前发布为 `test1`。软件校验和 ARM Cortex-A72 模拟执行记录随包提供，接下来需要在开发板完成 HDMI 首启、声音、手柄、游戏和 eMMC 启动检查。

复建入口见 [构建说明](docs/BUILD.md)。
