# 发行验证记录

构建环境：Linux x86_64，Ubuntu 22.04 容器，ARM64/ARM32 GCC 11.4。目标为原版 Firefly-RK3399 DDR3，TF 启动、HDMI 显示和音频。

已执行：

- 官方基础镜像 MD5 与本次输入 SHA256 校验。
- 自编 U-Boot/TF-A：31 项检查，覆盖 DDR3 TPL、SPL、TF-only 策略、无 MMC 持久环境、FIT/ELF 及实际二进制对应关系。
- Linux 6.6.27 设备树与实际镜像内核配置：82 项通过；重复构建设备树哈希一致。
- 6 个用户态适配文件的 18 项行为检查：风扇与 RG552 检测的板型判断、升级保护、路径边界、脚本语法。
- 重建入口的 14 项小夹具检查。
- FAT 空闲区域清零工具的 19 项检查；实际清零前后，对全部非空闲字节核对 SHA256，保留启动文件、文件系统元数据和 SHARE。
- SquashFS 全部 59,260 个原有路径的元数据核对：属主、权限、符号链接保留；新增 1 个 Firefly HDMI 配置。
- 两份 SquashFS 完整导出后，对每个普通文件计算 SHA256：46,805 个保留文件内容一致，5 个修改文件与适配器产物一致，新增 1 个配置，无删除文件。

原始压缩尝试发现 9 个 SDLPop 单字节全零文件被改变；最终使用 `-no-duplicates -no-sparse` 重新打包，所有文件大小与完整内容核对通过。具体失败样本保留在 `verification-evidence/failed-pack1-differences.json`，重建脚本已固定该打包参数。

最终整盘验证记录在发行目录 `validation/image.json`：从镜像重新读出 MBR、FAT、ext4、实际启动字节、设备树、内核与 initrd、完整 SquashFS，并检查 gzip 解压字节数及整盘哈希。

## 首次上板记录

待用 TF 卡启动原版 Firefly-RK3399，依次记录：HDMI 开机与声音、USB 手柄、以太网协商速度、Wi-Fi、蓝牙手柄、游戏运行及重启。当前内核缺少 RT5640 模拟音频和 HDMI-CEC 驱动，首版使用 HDMI 音频。
