# Firefly RK3399 Batocera 40 · eMMC

原版 Firefly-RK3399 DDR3 开发板的 eMMC 镜像，以及自带固件的 TF 安装卡。

- `batocera40-firefly-rk3399-emmc-test1.img.gz`：板载 eMMC 用户区整盘镜像。
- `batocera40-firefly-rk3399-emmc-installer-tf-test1.img.gz`：用 Etcher 写入 TF 卡，开机后运行安装程序；卡内已包含 eMMC 固件。

先阅读 [eMMC 安装说明](docs/eMMC安装说明.md)。安装会清空板载系统，可先完整备份 eMMC 用户区。安装器默认只做检查；执行 `--write` 才写入，完成后完整读回 SHA256。

板级更改：

- 自编 eMMC 专用 DDR3 TPL/SPL、U-Boot 2024.01 和 TF-A 2.10；SPL 只读 eMMC，U-Boot 优先 TF 救援卡 `mmc1`，没有可启动 TF 时进入 eMMC `mmc0`，无持久环境，启动阶段最高 52 MHz。
- Linux eMMC 控制器与 PHY 启用，保留板级 8 位、1.8 V 配置；采用 HS200，禁用 HS400/增强选通。
- eMMC 系统根参数固定 `dev=/dev/mmcblk2p1`；安装卡根参数固定 `dev=/dev/mmcblk1p1`，保持挂载与扩容对象明确。
- 内核、initrd 和 SquashFS 内容沿用已经逐文件核对过的 Firefly TF 版。

目录说明：`boot/` 是引导构建与验证，`kernel/` 是设备树，`flash/` 是板上安装程序和离线测试，`make-image.py` 负责只写普通文件的镜像组装，`verify-image.py` 独立检查成品。

原 TF 首测镜像及其发布文件保留在项目 `outputs/`，本次产物在 `outputs/emmc/`。eMMC 实际读写速度、独立开机和硬件表现随首次刷卡记录；当前使用 HDMI 音频，没有 RT5640 模拟音频与 HDMI-CEC 驱动。

无需联网的本地操作入口见 [本地键盘安装](docs/无网络时本地安装.md)。
