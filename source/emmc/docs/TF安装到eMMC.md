# 用 TF 安装卡将 Batocera 写入 eMMC

适用于原版 Firefly-RK3399 DDR3 开发板。使用 **TF 安装卡镜像**，不是此前禁用了 eMMC 的普通 TF 版。安装卡内已经放好独立的 eMMC 镜像、校验记录和安装程序，无需把压缩文件手工拷入卡。

建议 16 GB 或更大的 TF 卡，板载 eMMC 标称 8 GB 或更大。安装程序核对实际用户区容量至少 7 GiB，并要求镜像范围和末尾清理区域不重叠。

## 1. 启动安装卡

1. 用 balenaEtcher 将本版 `...installer...img.gz` 写入 TF，等待写入及验证完成。
2. 板卡断电插卡。先接 HDMI、USB 键盘/手柄及网线，再接正确的独立电源。
3. 等待进入 Batocera。从路由器找到 `BATOCERA` 的 IP。
4. 电脑用 SSH 登录：`ssh root@板子的IP`。Batocera 默认密码是 `linux`。

## 2. 只读检查

```sh
python3 /boot/emmc/install-to-emmc.py
```

程序确认原版板型、当前系统在 TF、目标确为 `fe330000` 控制器的 eMMC，检查 CID、容量和镜像的压缩/解压 SHA256。显示 `CHECK PASS` 后继续。

如果提示旧 eMMC 分区挂载在 `/media/...`，正式安装时会普通卸载它们；忙碌的挂载不会强制卸载。若提示 `/boot` 或 `/userdata` 不在 TF，先停止，不修改脚本里的设备号绕过检查。

## 3. 选择备份并安装

**正式安装会覆盖板载 eMMC 原系统和数据。**两种命令只选一种。

保留旧系统：TF 的 SHARE 分区需要至少“eMMC 实际完整容量 + 64 MiB”的空闲空间。例如 16 GB eMMC，建议使用 32 GB 或更大的 TF 安装卡。

```sh
python3 /boot/emmc/install-to-emmc.py --write --backup-dir /userdata/emmc-backup
```

程序先保存并核对整个 eMMC 用户区备份，成功后才开始安装。备份及其 SHA256/CID 记录位于指定目录，安装后可从 TF 导出保存。

明确不需要旧系统数据时：

```sh
python3 /boot/emmc/install-to-emmc.py --write --no-backup
```

写入过程会显示进度。程序独占 eMMC，阻止正在使用的文件系统或重新自动挂载干扰写入；写完后同步、清除读缓存并回读完整镜像范围核对 SHA256，还会清零并核对 eMMC 末尾 1 MiB，移除旧 GPT 备份表。

## 4. 从 eMMC 开机

必须看到 `INSTALL PASS`。运行：

```sh
poweroff
```

等待关机，断电，拔出 TF，再上电。首启等待约 5–10 分钟，检查 HDMI 画面、声音、USB 手柄和网络。程序不会自行关机。

安装报告保存在 TF 的 `/userdata/system/logs/emmc-install-时间.json`。若报 `STOP` 或 `FAIL`，保留 TF 和错误输出；不要把失败状态当作已经写好。

本安装过程只写 eMMC 用户区，保留 boot0、boot1、RPMB 及硬件启动分区配置。若拔 TF 后仍进入旧系统，应读取旧引导和 eMMC 启动配置后处理，不盲目改写硬件启动分区。
