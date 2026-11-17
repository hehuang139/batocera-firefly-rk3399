# 43.1 验证记录

本版在 Ubuntu 22.04 Docker 构建环境生成，ARM 程序使用 QEMU Cortex-A72 执行。详细记录随发布包 `validation/` 提供。

已执行：

- 官方 43.1 发布包 MD5 与固定 SHA256 校验。
- 主系统全量修改比较：53,361 个普通文件保持官方内容，模块目录完整替换为匹配的 6.6.27 BSP，改动在来源清单中逐项记录。
- 压缩主系统完整解包：68,574 个路径的文件内容、类型、权限、UID/GID、时间戳和符号链接逐项比较。
- 官方第二层完整解压和 103 个 ARM64 libretro 核心检查；主层优先的合并依赖路径检查。
- Python 3.12.8、RetroArch 1.22.2、EmulationStation、Labwc 0.9.3 和 configgen 的 Cortex-A72 执行；6 个常用 libretro 核心实际加载、初始化和退出。
- 从实际内核提取配置，核对 MMC、压缩、文件系统、OverlayFS、Panfrost 等功能。43.1 initrd 的 BusyBox 和启动脚本在 Cortex-A72 下执行，覆盖 TF/eMMC 和双层挂载参数。
- Select 热键配置、启动同步、更新保护，以及文件生成脚本的输入边界检查。

整盘最终检查见 `emmc-image.json` 与 `installer-image.json`：检查 MBR/FAT/SHARE、启动器与设备树、固定根设备、两层系统、全量模块及核心文件、内置 eMMC 固件与外部固件一致、压缩文件完整回读。

复建验证从两个固定官方发布包重新提取和应用适配；结果见 `rebuild-validation.json`。

下一步在原版 Firefly-RK3399 DDR3 上完成 HDMI 首启、声音、网络、手柄、游戏和 eMMC 拔卡启动检查；此包版本为 test1。
