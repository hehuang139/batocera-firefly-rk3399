# eMMC 安装入口：优先使用 TF 安装卡

本次 eMMC 镜像采用物理 eMMC 用户区从扇区 0 开始的整盘布局，包含 MBR、DDR3 初始化、U-Boot、启动分区和 SHARE。

推荐随本版提供的 **TF 安装卡镜像**。它先从 TF 启动 Linux，再确认板型、控制器路径与 eMMC CID，由 Linux `/dev/mmcblk2` 写入实际用户区；这条路径不依赖板上旧 Loader 的地址换算。安装脚本默认只检查，显式 `--write` 才会覆盖板载系统。

## 为什么不直接套用 `rkdeveloptool wl 0`

Rockchip 的 Rockusb 文档说明：部分旧 Miniloader 的 `wl` 地址存在 `0x2000` 扇区平移，USB 显示 `Loader` 并不能证明扇区 0 是物理用户区扇区 0。`rkdeveloptool db` 接收专门的 DDR/USB RAM loader 包；镜像内的 `idbloader.img` 是介质启动格式，不能拿它执行 `db`。

本项目没有把某个未知 USB Loader 的 `wl 0` 作为安装前提，也不要求清除 eMMC、短接芯片引脚或切换 eMMC 硬件启动分区。

## TF 尚未启动时

先按安装卡说明写 TF、接 HDMI 并独立供电。若仍进入原 eMMC 系统，记录原系统、完整板型及启动画面，再确认已有引导器如何选择 TF。Recovery 不是通用的“强制 TF”开关。

有 USB 数据线时，可以只读枚举 Rockusb 模式以辅助定位，不能将“发现 Loader”直接等同于可整盘烧录。若以后使用 USB 写入，应先确定：原版 RK3399 的匹配 DDR/USB loader、eMMC 选择、物理 LBA 映射、实际容量、完整备份及写后回读方法；再生成与之匹配的刷写流程。

相关来源：

- Rockchip Rockusb 协议：https://opensource.rock-chips.com/wiki_Rockusb
- 官方 rkdeveloptool 使用说明：https://github.com/rockchip-linux/rkdeveloptool/blob/master/Readme.txt
- 本项目 Linux 6.6.27 MMC alias 证据：`source/docs/integration-evidence/`。
