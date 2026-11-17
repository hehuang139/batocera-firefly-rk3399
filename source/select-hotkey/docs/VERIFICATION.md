# Select 热键 test2 验证记录

构建环境为 Linux x86_64、Ubuntu 22.04 构建容器。镜像沿用 Firefly RK3399 eMMC test1 的启动器、设备树、Linux 6.6.27 和系统 SquashFS，新增 Batocera 原生 saved overlay。

本次实际执行：

- 热键行为 29 项：257 个默认手柄配置、不同按钮编号/evdev code、首次配对与保存后重载、保留既有命令、幂等和备份，以及实际 configgen / RetroArch 配置输出。
- 独立运行时检查 6 项：配置异常、写入失败、备份和并发编辑保护。
- 集成边界检查 26 项：固定文件集合、执行权限、路径与符号链接、覆盖拒绝、test2 固件身份及完整 ext4 文件内容。
- 正式 overlay 检查 42 项：16 MiB ext4、无日志且 clean、只读 e2fsck、实际文件哈希、root 属主、目录与执行权限。
- 验证器夹具 5 项：正常文件系统，以及脏文件系统、错误属主、额外符号链接、错误执行权限的拒绝。
- 重建脚本 18 项：小文件与明确桩程序验证干净源码树流程、输入前置校验、两种镜像及验证器调度、错误传播。

整盘验证器分别读取两份最终镜像，核对实际启动字节、分区、设备树、内核、initrd、SquashFS、SHARE、保存的 overlay、文档、压缩文件和完整解压哈希；TF 安装镜像中的 eMMC 固件还会再次解压，与独立 eMMC 镜像匹配。最终计数及结果见 validation/image-emmc.json、validation/image-installer.json。

实际 initrd 的 saved overlay 在 switch_root 前载入；S12 初始化 SHARE，S30 应用 Select 设置，S31 启动 EmulationStation。原启动器、设备树和 eMMC 安装程序的已有验证记录也随包提供。

实板首启步骤：启动 TF 安装卡、验证 Select + Start 退出游戏，写入 eMMC 并完成回读校验，关机拔 TF 后检查 eMMC 独立启动、手柄、HDMI 声音和网络。
