# Firefly RK3399 设备树

面向原版 Firefly-RK3399 DDR3 开发板的 Batocera 40 TF 首启版，使用官方 RockPro64 镜像中原封不动的 Linux 6.6.27 内核和模块。Linux 设备树独立编译；系统中的 `batocera.board` 应设为 `firefly-rk3399`。

## 源码和修改

- `linux-6.6.27/`：Linux v6.6.27 的 Firefly DTS 及完整 include 依赖和许可，共 18 个文件。上游 Git 中的 `linux-event-codes.h` 是符号链接，重建脚本按记录恢复链接，再进行预处理。
- `batocera-patches/`：Batocera 40、提交 `f7dabcebc82ed66fb740727d64913e2e86fc1d6e` 的有效 RK3399 Linux 补丁。`manifest.json` 记录每个补丁及其目标路径；重建只应用与此板设备树依赖相关的 6 个补丁文件中的对应 diff，`patch --fuzz=0`，补丁顺序与文件名顺序一致。
- `rk3399-firefly-batocera-sd.dts`：启用 HDMI 声卡；禁用 eMMC 控制器及 PHY；保留 SDIO Wi-Fi；把 CPU 温控阈值恢复为 Linux 上游的 70/75/95°C；添加工作灯心跳。
- USB hub 的 GPIO2_A4 复位、FUSB302 的 `fairchild,fusb302` 匹配名、蓝牙 UART0 serdev 配置来自 Armbian 的原版 Firefly 板补丁。完整参考补丁、提交 URL 和 SHA256 随包保存。没有引入参考补丁中不相关的供电/PCIe更改，也没有把 Wi-Fi 中断类型改成 GPIO 极性值。
- `base-kernel.config` 从交付基底镜像 `boot/linux` 的 IKCONFIG 提取；另保存 Batocera 源码配置，便于比对。

## 重建与验证

在项目根目录运行（输出到 `work/kernel/`）：

```sh
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD:/build" -w /build firefly-rk3399-fullbuilder:20261108 \
  bash source/kernel/build-dtb.sh

docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD:/build" -w /build firefly-rk3399-fullbuilder:20261108 \
  python3 source/kernel/validate-dtb.py

docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD:/build" -w /build firefly-rk3399-fullbuilder:20261108 \
  python3 source/kernel/check-reproducibility.py
```

安装了 gcc、dtc、fdtget、patch、Python3 的 Linux 主机也可以直接执行上述脚本。`FIREFLY_KERNEL_WORK` 可指定构建目录。源文件和补丁逐项 SHA256 检查在编译前执行。

验证结果：82 项编译后设备树属性及实际内核配置检查通过；从原始源码重新应用补丁编译后 DTB 的 SHA256 相同；与未适配 Firefly DTS 对照，10 类警告位置/签名相同，无新增警告。现存警告来自上游 USB 容器无 reg、DSI 地址大小、PCIe/PCIe-EP 共地址和 GPIO 中断控制器缺 address-cells。

DTB SHA256：`72b0af6f24ebec0334888b5e6b223390fddb657abe23fb13e1a7cd39314b6446`。

## 使用范围

- HDMI 显示、HDMI PCM 音频、Panfrost GPU、USB Host、千兆 MAC、SD、SDIO Wi-Fi、蓝牙 serdev 的设备树和内核驱动均已对照检查。蓝牙由内核装载，启动脚本不能再对 UART0 执行 hciattach；固件需要 BCM4356A2.hcd，Wi-Fi 需要对应的 brcmfmac4356 SDIO 固件和板级 NVRAM。
- 官方基底没有启用 RT5640 模拟音频编解码器驱动，因此本版使用 HDMI 音频；没有启用 HDMI-CEC 驱动。
- 官方基底未启用专用 Realtek PHY 驱动，以通用 PHY 处理。首次上板时用有线网络检查链路与实际协商速度。
- TF 版本禁用 eMMC，避免启动后自动挂载原有 eMMC。不能直接把此 DTB 当作 eMMC 版本使用。
- 本目录验证覆盖源代码、编译产物及驱动配置。实际 HDMI 音画、Wi-Fi/蓝牙、手柄和游戏运行由首次上板测试确认。

Linux 原文和参考补丁保留各自许可。新增脚本为 MIT；新增 DTS 为 GPL-2.0-or-later 或 MIT 双许可。
