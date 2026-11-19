# Firefly RK3399 · Batocera 43.1

> **原版 Firefly-RK3399 DDR3 Rev 1.0 请暂缓用 test1 直刷或用其 TF 安装卡。** 实际 Linux DTB 的 CPU 大核休眠 bank 为 0；同一板在 Ubuntu 复现冷启动失败。见 [VSEL 检查和直刷版替代办法](VSEL.md)。

[下载 43.1 Release](https://github.com/hehuang139/batocera-firefly-rk3399/releases/tag/v43.1-firefly-emmc-test1) · [分卷下载与合并](下载与合并.md)

43.1 版使用官方 Batocera 43.1 ARM64 用户态、完整模拟器附加层及 Linux 6.6.27 Firefly 板级驱动。支持 eMMC、TF 救援及自带固件的 TF 安装卡，手柄 Select 作为 Hotkey。

- [43.1 版本与来源](source/v431/README.md)
- [eMMC 安装说明](source/v431/docs/eMMC安装说明.md)
- [Select 热键](source/v431/docs/Select热键.md)
- [复建说明](source/v431/docs/BUILD.md)

当前为 test1，软件验证报告随包提供；刷卡后完成 HDMI 首启和实际游戏检查。下方保留旧版说明。

# Batocera 40 既有版本

原版 Firefly-RK3399 DDR3 开发板的 TF 卡适配镜像，面向 HDMI 显示器、USB 手柄和有线网络。

以 Batocera 官方 RockPro64 40（2024-08-01）为系统基底，保留其 Linux 6.6.27、ARM64 模拟器、EmulationStation、Mesa Panfrost 和游戏配置。针对 Firefly 自编 U-Boot 2024.01、TF-A 2.10、DDR3 初始化和设备树，并修正通用 RK3399 用户态中与其他板子相关的启动脚本。

- 下载文件：`outputs/batocera40-firefly-rk3399-sd-test1.img.gz`
- [刷卡与首启](source/docs/刷卡与首启.md)
- [构建说明](source/docs/BUILD.md)
- [设备树和驱动](source/kernel/README.md)
- [启动程序](source/boot/README.md)
- [用户态适配](source/rootfs/README.md)

适配包含 HDMI 音频、USB hub 复位、FUSB302、AP6356S Wi-Fi 固件与蓝牙 serdev、上游温控阈值及 Firefly 更新保护。首版禁用 Linux eMMC 控制器，TF 启动器只搜索 TF；不能用于 ROC-RK3399-PC、Core-3399J 等其他型号，也不能直接刷入 eMMC。

当前内核不包含 RT5640 模拟音频和 HDMI-CEC 驱动，使用 HDMI 音频。无线连接、千兆协商、手柄和游戏帧率需在首次上板时检查。验证报告记录已执行的编译、配置、整盘及压缩包检查；硬件启动结果待刷卡回传。

## eMMC 版

`outputs/emmc/` 提供板载 eMMC 固件和自带固件的 TF 安装卡。安装后拔 TF 可从 eMMC 开机；以后可插安装卡重装。详见 [eMMC 安装说明](source/emmc/docs/eMMC安装说明.md) 和 [eMMC 适配源码](source/emmc/README.md)。

## Select 热键版 eMMC test2

新增版本位于 `outputs/emmc-test2/`，推荐使用其中的 TF 安装镜像。每只手柄的 Hotkey 跟随 Select，Select + Start 退出游戏；新配对/重新映射后也生效。源码与重建入口见 `source/select-hotkey/README.md`。系统仍以 RK3399 官方稳定镜像 Batocera 40 为基底；2026-11-08 全局稳定版为 43.1。
