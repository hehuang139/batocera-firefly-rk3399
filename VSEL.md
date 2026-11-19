# Firefly-RK3399 DDR3 Rev 1.0 稳压器检查

43.1 test1 的 eMMC 直刷镜像和 TF 安装卡均使用 Linux 6.6.27，内建 `CONFIG_REGULATOR_FAN53555=y`。两种介质的 `extlinux.conf` 都指向 `/boot/rk3399-firefly-batocera-emmc.dtb`，实际 DTB 的 CPU `0x40` 和 GPU `0x41` 选择器为 `0/1`，两路均为 `regulator-off-in-suspend`。TF 安装卡还包含与直刷版相同 SHA-256 的内置 eMMC 固件。U-Boot 自身的 FIT 控制树是另一份文件。

Rev 1.0 的大核运行在 VSEL0，这个配置在同板 Ubuntu 上导致驱动绑定时关断运行供电，见 [实板和驱动复盘](https://github.com/hehuang139/ubuntu-firefly-rk3399/blob/v22.04.5-vsel1-test2/docs/vsel.md)。Batocera 40 的早期 TF、eMMC 和 Select 热键版也从归档整盘读回了 `0/1`；两张安装卡内嵌的镜像分别与对应直刷整盘逐字节一致。上述 Batocera 版本没有本次板上的启动测量。

## 43.1 eMMC 直刷版的替代方法

在 Linux 装好 Python 3 和 `mtools`，按本仓库的发布说明下载并合并 `batocera431-firefly-rk3399-emmc-test1.img.gz` 分卷，再解压成 `.img`。保持下载的原文件。用以下命令生成另一个普通文件：

```sh
python3 source/v431/repair-emmc-vsel.py \
  batocera431-firefly-rk3399-emmc-test1.img \
  batocera431-firefly-rk3399-emmc-vsel1.img
```

工具要求原镜像匹配本项目 test1 的整盘 SHA-256，按实际 FAT 目录核对 Linux 启动路径和原 DTB，只修改 CPU 大核对应的一个字节（`0/1` → `1/1`），并从 FAT 读回验证。GPU 和休眠约束保持原样。修订整盘的 SHA-256 为 `92a916225d2b9239f0ca8e4570c316b55a914332f52c2cefa76dd36f370dc598`。已从 GitHub 下载两卷并校验后重组和解压；对原版和修订版做整盘比较，只有偏移 427277359 的一个字节（从 0 开始计）改变。生成后可按原 eMMC 直刷文档写入新的 `.img`，备份目标 eMMC 后再操作。此方法只适用于 43.1 直刷镜像，不接受 TF 安装卡或旧 40 镜像。

## 43.1 TF 安装卡的替代方法

从 [VSEL1 test2](https://github.com/hehuang139/batocera-firefly-rk3399/releases/tag/v43.1-firefly-vsel1-test2) 选择 TF 安装卡或 eMMC 直刷版。要从本地的旧发布件重做 TF 卡，先按上一节生成正确的 eMMC `.img`，再运行：

```sh
gzip -1 -n -k batocera431-firefly-rk3399-emmc-vsel1.img
python3 source/v431/repair-installer-vsel.py \
  batocera431-firefly-rk3399-emmc-installer-tf-test1.img \
  batocera431-firefly-rk3399-emmc-vsel1.img.gz \
  batocera431-firefly-rk3399-emmc-installer-tf-vsel1.img
```

工具校验原 TF 整盘与原嵌入镜像的 SHA-256，修复外层启动 DTB，把正确的 eMMC gzip 与匹配清单一起写入新文件。它会逐一比对 FAT 其余文件、引导区和 SHARE 分区，再读回核对 DTB、清单和内嵌镜像。内嵌文件名保持原安装器默认值；内容和清单都已更新。工具只处理普通镜像文件。发布版 TF 整盘 SHA-256 为 `aa5072e03063936de926ef3df30216af1b4513d21427f486833b94f613f01866`。本地重做的 FAT 写入时间及 gzip 工具可能不同，以脚本回读和报告的实际哈希为准。

## 从原构建材料重建

`source/v431/vsel1-rebuild.patch` 适用于 test1 对应的完整构建材料。从构建材料的副本顶层执行 `patch -p1` 应用补丁。共享 DTS 覆盖修正大核 bank，保留 GPU 和休眠约束。用 DTC 1.6.1 运行 `source/emmc/kernel/build-dtb.sh`，把新生成的 `work/emmc/kernel/rk3399-firefly-batocera-emmc.dtb` 放到副本的 `source/v431/assets/`。沿用原 `source/v431/rebuild.py`，为修订件指定新的输出目录。已更新输入清单和从成品 extlinux 路径读取 DTB 的验证器；验证器依次核对三处供电引用、实际芯片、selector 和休眠状态。

用归档材料重新编译，原 eMMC DTB 构建检查 39/39，生成的 DTB SHA-256 `f6e6455b3b717c4cd19fd45676e8a4a93a885b8f4da08ff100f6b6a08c452669`，和修订 TF/eMMC 读回一致。新的成品 DTB 验证接口对两份修订件通过，对旧件报出 `dtb-vsel:/cpus/cpu@100: 0`。
