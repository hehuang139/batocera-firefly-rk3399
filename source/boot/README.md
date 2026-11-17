# Firefly RK3399 TF 启动组件

目标是原版 Firefly-RK3399（DDR3），采用 U-Boot v2024.01 自带的 DDR3 TPL、SPL 和主程序，以及从源码构建的 TF-A v2.10。没有使用其他 RK3399 板卡的 DDR 初始化二进制。

## 配置

- 原始 `firefly-rk3399_defconfig`，DDR3 1600 MT/s（800 MHz）。
- U-Boot 的 `mmc1` 为 TF，`mmc0` 为 eMMC。SPL 只从 `sdmmc` 读后续程序，系统启动只扫描 `mmc1`。
- 环境保存在内存，`CONFIG_ENV_IS_NOWHERE=y`，不读取或写入存储中的环境。
- 禁用 U-Boot 视频，交给 Linux 初始化 HDMI；串口为 UART2，1500000 8N1。
- 内核设备树由镜像组装步骤提供，本目录的 `u-boot.dtb` 只用于启动程序自身。
- TF-A 的 Cortex-M0 小固件使用已有 ARM32 交叉编译器，构建脚本给该子目录添加 `-fno-pie` / `-no-pie`，关闭 Ubuntu 工具链默认的 PIE 以适配上游裸机链接脚本。

## 重建

在项目根目录运行 `source/boot/rebuild-boot.sh`。默认使用 `firefly-rk3399-fullbuilder:20261108` 容器，以无网络模式构建。两个公开上游源码归档及 SHA256 校验值随本目录保留。

输出位于 `work/boot/assets/`：

- `idbloader.img`：放在整盘偏移 32768 字节（LBA 64）。
- `u-boot.itb`：放在整盘偏移 8388608 字节（LBA 16384）。
- `u-boot-rockchip.bin`：包含前两者，放在偏移 32768 字节；与分别写前两份是两种替代布局。

这些文件用于构造磁盘镜像；不是 Rockchip USB 下载器，不能作为 `rkdeveloptool db` 输入。

TF 镜像只有在板卡实际选择 TF 启动时才会执行此程序。板载原有启动器可能先被执行，写入 TF 卡本身不会改变芯片启动顺序。
