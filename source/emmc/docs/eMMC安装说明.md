# Firefly RK3399 · Batocera 40 · eMMC 安装

适用原版 **Firefly-RK3399 DDR3 开发板**。板载 eMMC 至少为标称 8 GB（安装脚本要求实际用户区容量不小于 7 GiB）。本次安装会替换 eMMC 上原来的系统与分区；需要保留的数据先备份。

## 推荐：使用自带固件的 TF 安装卡

准备 16 GB 或更大的 TF 卡、读卡器、HDMI 显示器、网线、USB 键盘/手柄和开发板独立电源。

1. 下载 `batocera40-firefly-rk3399-emmc-installer-tf-test1.img.gz`。这是给 **TF 卡**写入的安装环境，里面已放好 eMMC 固件。
2. 用 balenaEtcher 直接选择该 `.img.gz`，核对 TF 卡的名称与容量后写入并等待验证。写卡会清空 TF 卡。电脑提示格式化分区时取消。
3. 板子断电插 TF 卡，先接 HDMI、有线网络、USB 键盘/手柄，再接电源。首次启动等待数据分区准备完成，进入 Batocera 界面。
4. 在网络设置或路由器中找到板子的 IP，在电脑终端连接：

   ```sh
   ssh root@板子的IP
   ```

   默认密码为 `linux`。先做只读检查：

   ```sh
   python3 /boot/emmc/install-to-emmc.py
   ```

5. 检查输出应识别到原版 Firefly、TF 上的运行系统，以及板载 eMMC `/dev/mmcblk2`，并且镜像校验通过。然后选择下面一种写入方式。

   **有足够 TF/外部存储空间，先备份完整 eMMC 用户区再写入：**

   ```sh
   python3 /boot/emmc/install-to-emmc.py --write --backup-dir /userdata/emmc-backup
   ```

   备份是未压缩的完整 eMMC 用户区，剩余空间必须大于 eMMC 容量；不包含 eMMC boot0/boot1 和 RPMB。请按原系统实际使用情况另保留这些区域。若 TF 空间不足，可换更大 TF 卡，或按脚本说明选择外部磁盘目录。

   **已备份所需数据，接受清空 eMMC 原系统：**

   ```sh
   python3 /boot/emmc/install-to-emmc.py --write --no-backup
   ```

6. 等待写入、完整读回 SHA256 校验和旧 GPT 尾部清理全部成功，期间不要断电。只有脚本明确报告成功后再运行：

   ```sh
   poweroff
   ```

7. 等待关机后切断电源，**拔掉 TF 卡**，再给板子上电。此时由 eMMC 独立启动。第一次启动会扩展 eMMC 的 SHARE 数据分区，等待约 5–10 分钟。

## 两种镜像不要选错

| 文件 | 写入位置 | 用途 |
| --- | --- | --- |
| `batocera40-firefly-rk3399-emmc-installer-tf-test1.img.gz` | TF 卡 | 推荐入口，包含系统、安装脚本和 eMMC 固件 |
| `batocera40-firefly-rk3399-emmc-test1.img.gz` | eMMC 用户区 | 板载系统的整盘镜像，安装卡已经内置，无需重复复制 |

两者都是整盘镜像，均不是 Rockchip `update.img`。eMMC 版使用专用启动器：SPL 从 eMMC 读取 U-Boot，U-Boot 优先检查 TF 救援卡、没有可启动 TF 时启动 eMMC，正式 eMMC 系统的 Linux 根分区固定为 `/dev/mmcblk2p1`。安装卡从 TF `/dev/mmcblk1p1` 启动，同时开放 eMMC 控制器供安装程序使用。

## 启动、校验与排查

- 安装卡只会在手动执行 `--write` 后写 eMMC。默认命令只读检查。它核对板型、MMC 类型、物理控制器、容量、挂载来源和镜像哈希，并拒绝覆盖正在运行的系统。
- 写入完成后按原始镜像长度完整回读，核对 SHA256；eMMC 末尾 1 MiB 清零并检查，防止旧 GPT 备份表干扰扩容。
- 如果插安装卡仍进入旧系统，先记录屏幕和板载旧系统信息。芯片可能优先加载已有 eMMC/SPI 启动器；Recovery 按键不保证强制 TF 启动。不要把 `idbloader.img` 当成 USB RAM Loader，也不要直接尝试未知 Loader 的 `wl 0`。
- 正式 eMMC 系统的根设备固定为 eMMC，不按卷标选盘。以后需要重装时，断电插入本版 TF 安装卡即可进入 TF 安装环境；正常使用时拔掉 TF 卡。
- 若报设备忙、挂载源不符、校验失败，停止后按提示保存日志，不能把失败当成刷写成功。安装脚本不会自动重启。
- 当前版本使用 HDMI 音频；内核没有 RT5640 模拟音频和 HDMI-CEC 驱动。eMMC 首启后检查 HDMI 声音、USB 手柄、有线网络、Wi-Fi/蓝牙、游戏和重启。

日志采集：

```sh
sh /boot/collect-logs.sh
```

通用在线升级已关闭，后续应使用这个 Firefly 项目的匹配版本更新。
