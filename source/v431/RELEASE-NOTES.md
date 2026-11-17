# Batocera 43.1 Firefly RK3399 eMMC test1

面向原版 Firefly-RK3399 DDR3，新增真实 Batocera 43.1 ARM64 系统适配。官方版本字符串保留为 `43.1 2026/06/01 19:14`，采用官方双 SquashFS 布局，附加层含 103 个 libretro 核心。

板级使用 Linux 6.6.27、匹配模块、Firefly 设备树与 DDR3 启动器，Mesa / Panfrost、Wayland / Labwc 和模拟器程序来自 43.1。默认 HDMI 音频，使用网线可进行首启检查。保留 eMMC 独立启动和 TF 救援优先策略。

提供两种镜像：eMMC 用户区整盘镜像，以及内置同一固件的 TF 安装卡。TF 安装卡只在手动执行安装命令后写 eMMC。安装会替换板载旧系统及分区；先按安装说明备份。建议至少 16 GB TF、标称至少 8 GB eMMC。

每只手柄以自己的 Select / Back / View 为 Hotkey，Select + Start 退出游戏；重新配对、保存按键后自动同步。通用在线升级关闭，更新需要使用此 Firefly 适配版本。

旧版 Batocera 40 文件保留。本次 test1 的软件检查、完整镜像验证和复建验证记录随包提供，接下来完成上板首启和游戏检查。
