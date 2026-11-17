# 43.1 ARMv8 用户态与 RK3399 内核检查

`verify-runtime.py` 只读检查已提取的实际 43.1 rootfs，随后用 QEMU AArch64 的 `cortex-a72` CPU 模型执行 Python、RetroArch、EmulationStation、Labwc 和 configgen 的版本/导入入口。依赖闭包由 ELF64 动态表独立解析，包含解释器、RPATH/RUNPATH、每个 NEEDED 库的架构和哈希。不会向 rootfs 注入 QEMU 或其他文件。

```sh
python3 source/v431/runtime/verify-runtime.py \
  --rootfs /stage/rootfs \
  --report source/v431/runtime/runtime-validation.json
```

运行环境需要 `qemu-aarch64-static` 与 `modinfo`，由 `source/v431/Dockerfile` 安装。使用 `firefly-rk3399-v431builder:20261117` 容器。

此 ES 提交的 `--help` 输出版本，源码没有 `--version` 分支；后者会进入图形启动流程。验收因此使用实际支持的 `--help` 入口。

`provenance/` 保留两份 43.1 板级配置及 Mesa 25.3.6 / Linux 6.6 Panfrost 接口源码。两个平台都使用 ARMv8-A AArch64 NEON、Mesa Panfrost 与 Wayland/Labwc。Mesa 的 Panfrost kmod 后端最低接受 DRM 1.1，Linux 6.6 Panfrost 提供 1.2；新增时间戳、标签和优先级查询具备能力/版本检查。统一 Gallium 库包含 Midgard / Mali-T860 实现。内核配置和完整模块必须与保留的 RK3399 6.6.27 内核一致。Panfrost 为内置驱动，使用实际内核配置和 modules.builtin 联合检查；brcmfmac 为模块，通过 modinfo 核对 vermagic。

这组检查执行用户态 CPU 和加载器入口，并检查 GPU 驱动接口；实际 HDMI、GPU 绘制、声音和手柄操作由板卡首启检查。

43.1 官方镜像使用双层系统：主层 `batocera` 和第二层 `rufomaculata`，主层文件优先。103 个 libretro 核心位于第二层，不能只检查主层就判断核心缺失。`verify-secondary.py` 对全部核心解析两层合并后的 AArch64 ELF 依赖闭包，并调用目标 Python 的 ctypes，在 Cortex-A72 QEMU 中对 FCEUmm、Gambatte、Genesis Plus GX、mGBA、Snes9x、Snes9x 2010 执行 API 版本、系统信息、初始化及退出接口。无需游戏 ROM。

```sh
python3 source/v431/runtime/verify-secondary.py \
  --rootfs /stage/rootfs \
  --secondary-rootfs /stage/runtime-layer \
  --secondary-squashfs /stage/base-boot/boot/rufomaculata.update \
  --report source/v431/runtime/secondary-validation.json
```

第二层保持官方原文件的 367181824 字节，SHA256 为 `a2eb67cd4839d0f129a5aec0b4fe7c3df2d6c0208a40466c775ecea335e22197`。`secondary-validation.json` 记录核心清单、依赖文件来源与哈希，以及六次核心运行输出。

`rebuild-validation.json` 记录额外执行的完整离线复建：从两个原始下载包实际提取、应用适配、打包，并按固定发布哈希和全部文件元数据验收。主层系统大小 1845645312 字节，SHA256 `7b83b51b09184b210abe434eca0657fae6577ba7ea86096da8add2a7cfe74cbe`，与发布系统一致。
