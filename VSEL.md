# Firefly-RK3399 DDR3 Rev 1.0 稳压器检查

43.1 test1 的 eMMC 直刷镜像和 TF 安装卡均使用 Linux 6.6.27，内建 `CONFIG_REGULATOR_FAN53555=y`。两种介质的 `extlinux.conf` 都指向 `/boot/rk3399-firefly-batocera-emmc.dtb`，实际 DTB 的 CPU `0x40` 和 GPU `0x41` 选择器为 `0/1`，两路均为 `regulator-off-in-suspend`。TF 安装卡还包含与直刷版相同 SHA-256 的内置 eMMC 固件。U-Boot 自身的 FIT 控制树是另一份文件。

Rev 1.0 的大核运行在 VSEL0，这个配置在同板 Ubuntu 上导致驱动绑定时关断运行供电，见 [实板和驱动复盘](https://github.com/hehuang139/ubuntu-firefly-rk3399/blob/v22.04.5-vsel1-test2/docs/vsel.md)。在 Batocera 40 的早期 TF、eMMC 以及 Select 热键版的板级构建输入里也找到了同配置。上述 Batocera 版本没有本次板上的启动测量。

## 43.1 eMMC 直刷版的替代方法

在 Linux 装好 Python 3 和 `mtools`，按本仓库的发布说明下载并合并 `batocera431-firefly-rk3399-emmc-test1.img.gz` 分卷，再解压成 `.img`。保持下载的原文件。用以下命令生成另一个普通文件：

```sh
python3 source/v431/repair-emmc-vsel.py \
  batocera431-firefly-rk3399-emmc-test1.img \
  batocera431-firefly-rk3399-emmc-vsel1.img
```

工具要求原镜像匹配本项目 test1 的整盘 SHA-256，按实际 FAT 目录核对 Linux 启动路径和原 DTB，只修改 CPU 大核对应的一个字节（`0/1` → `1/1`），并从 FAT 读回验证。GPU 和休眠约束保持原样。修订整盘的 SHA-256 为 `92a916225d2b9239f0ca8e4570c316b55a914332f52c2cefa76dd36f370dc598`。已从 GitHub 下载两卷并校验后重组和解压；对原版和修订版做整盘比较，只有偏移 427277359 的一个字节（从 0 开始计）改变。生成后可按原 eMMC 直刷文档写入新的 `.img`，备份目标 eMMC 后再操作。此方法只适用于 43.1 直刷镜像，不接受 TF 安装卡或旧 40 镜像。不要用旧 TF 安装卡搬运修订版，它仍内置 test1。修订的 TF 安装卡应同时修复外层 DTB 和内嵌的 eMMC，重新生成校验清单再验证。
