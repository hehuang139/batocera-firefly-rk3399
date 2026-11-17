# 第三方来源与许可

新增构建脚本与文档使用 MIT 许可。既有源码、改编脚本、设备树、系统与固件沿用各自许可，顶层 MIT 不覆盖它们。

- Batocera 40 系统与模拟器：官方原始镜像及对应源码提交记录在 base-manifest.json。系统包含不同许可证的组件，原系统 `/usr/share` 及各项目的许可继续适用。https://batocera.org/license
- U-Boot 2024.01：GPL-2.0-or-later，完整源码归档及 Licenses/ 随 source/boot 提供。
- ARM Trusted Firmware 2.10：BSD-3-Clause 等，以完整源码归档内 license.rst 为准。
- Linux 6.6.27 DTS 与 dt-bindings：原文件 SPDX 标注保留，许可文本随 source/kernel/linux-6.6.27 保存。完整 Linux 对应版本：https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/tag/?h=v6.6.27
- Batocera 内核补丁和原版启动脚本：保留原文与来源，见 source/kernel/manifest.json、source/rootfs/provenance.json。
- Armbian Firefly DTS 参考和 AP6356S NVRAM 证据：固定提交、URL、哈希见 source/kernel/manifest.json 和 source/rootfs/wireless-audit.json。
- Broadcom 固件沿用官方基底中现有文件和许可，不在不同模块间替换校准数据。

如公开分发整盘镜像，应同时提供本适配源码包，并保留上述组件的对应源码与许可获取方式。

Batocera 43.1 适配位于 `source/v431/`。完整双层用户态与 initramfs 来自官方 Odroid N2+ 43.1 发布包，固定 SHA256、版本与上游源码提交见该目录 `provenance/`。本版保留原系统所有组件的原许可；移植文件的改动清单及对应原文件在 `rootfs/provenance.json`、`rootfs/upstream/`。RK3399 6.6.27 模块和 Broadcom 固件来自固定的官方 RockPro64 40 基底，内核、设备树与启动器的对应源码入口沿用以上说明。
