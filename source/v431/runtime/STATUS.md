# FROZEN — 2026-11-17

主层运行检查 35/35 PASS；第二层核心检查 217/217 PASS。

Cortex-A72 QEMU 执行 Python 3.12.8 标准库、RetroArch 1.22.2 版本、EmulationStation help/version、Labwc 0.9.3 和 configgen 导入均成功。七个主程序/图形库的 AArch64 ELF 依赖闭包完整。实际 RK3399 内核与唯一模块目录均为 6.6.27，Panfrost 为内置驱动，brcmfmac vermagic 匹配。Mesa 25.3.6 包含 Mali-T860，Panfrost DRM 接口版本检查兼容 Linux 6.6。

官方 43.1 第二层 rufomaculata 包含 103 个 libretro 核心；已按主层优先、第二层补充的真实 overlay 顺序检查全部核心依赖。六个常用核心 FCEUmm、Gambatte、Genesis Plus GX、mGBA、Snes9x、Snes9x 2010 在 Cortex-A72 QEMU 下完成 libretro API 版本、系统信息、init/deinit 调用，退出状态全部为 0。此前“缺少核心”的判断已由官方双层布局确认并纠正。

第二层原文件：367181824 字节，SHA256 a2eb67cd4839d0f129a5aec0b4fe7c3df2d6c0208a40466c775ecea335e22197。此目录中的两个 JSON 报告记录检查范围、依赖哈希与执行输出。运行检查没有修改镜像文件系统。

## 独立重建验证 PASS

离线 Docker 中从固定的两个原始发布包完整执行 rebuild.py --rootfs-only，退出 0。真实提取、适配、7 组行为检查、全树增量检查、SquashFS 打包与全部回读检查均通过。新系统层大小 1845645312 字节，SHA256 7b83b51b09184b210abe434eca0657fae6577ba7ea86096da8add2a7cfe74cbe，与冻结发布系统逐字节一致。回读验证 68574 路径、54216 普通文件内容及完整元数据。报告 source/v431/runtime/rebuild-validation.json，日志 logs/v431/rebuild-proof.log。无需修改重建脚本。
