# 构建与来源

## 固定输入

- 官方基底：`batocera-rk3399-rockpro64-40-20240801.img.gz`，1,812,540,335 字节。
- URL：https://mirrors.o2switch.fr/batocera/rockpro64/stable/last/batocera-rk3399-rockpro64-40-20240801.img.gz
- 官方 MD5：`09ecee0ed49d57555938320ea552278c`
- 本次输入 SHA256：`1c6049c177104c37b0172b65f5518fcf4ee54d510da1020d83ae10dcf2f7fa33`
- Batocera 40 源码：https://github.com/batocera-linux/batocera.linux/tree/f7dabcebc82ed66fb740727d64913e2e86fc1d6e

`source/base-manifest.json` 固定基底；`source/boot/` 内含 U-Boot/TF-A 源码包、构建配置、校验和；`source/kernel/` 含完整 DTS include 依赖、补丁清单和实际内核配置；`source/rootfs/` 含待改文件原文、出处、适配器和验证程序。

## 重建

需 Linux、Docker 及约 25 GB 空闲空间。在解压的项目根目录执行：

```sh
docker build -t firefly-rk3399-fullbuilder:20261108 source
mkdir -p downloads outputs
# 把上述固定的官方 .img.gz 放入 downloads/。
bash source/rebuild-image.sh \
  "$PWD/downloads/batocera-rk3399-rockpro64-40-20240801.img.gz" \
  "$PWD/outputs/rebuilt.img"
```

脚本自动执行启动器、设备树、rootfs 和整盘验证，并生成对应的 `.validation.json`。先重建启动器和设备树，再校验并解压官方基底，保留文件属主、权限及链接，应用 6 处用户态改动，关闭去重及稀疏优化，生成新的 SquashFS 与整盘镜像。镜像组装器只接受新的普通 `.img` 文件，不写块设备。容器中 root 用于保留原文件 UID/GID；挂载范围只包含项目目录，不挂载电脑磁盘设备。

Dockerfile 使用 Ubuntu 22.04 与系统交叉工具链。编译输入有固定校验；组装后只清零 FAT 标记空闲的簇，并核对其他全部字节的哈希保持不变，避免旧系统数据占用压缩包空间。不同工具链包版本及 FAT 写入时间可能改变整盘哈希，重新构建后检查自身输出的 SHA256 与验证报告。

## 布局

| 内容 | 起始位置 | 大小 |
| --- | --- | --- |
| MBR | 0 | 512 字节 |
| Firefly DDR3 TPL/SPL | 32 KiB | 149,504 字节 |
| Firefly U-Boot FIT（包含 TF-A） | 8 MiB | 以 manifest 为准 |
| BATOCERA FAT32 | 16 MiB / LBA 32768 | 4 GiB |
| SHARE ext4 | LBA 8421376 | 256 MiB，首启扩容 |

原始整盘镜像 4,580,179,968 字节。供体板的启动器和持久环境区域清零后，写入 Firefly 专用启动器。U-Boot 不保存 MMC 环境，Linux eMMC 控制器在本版关闭。

## 验证

`source/boot/validate-boot.py` 检查编译后的 DDR3、TF 启动顺序、ELF/FIT 结构和配置；`source/kernel/validate-dtb.py` 检查设备树与实际内核驱动；`source/rootfs/validate.py` 检查用户态规则和脚本行为。

`source/verify-image.py` 独立读取最终整盘镜像，检查分区、FAT/ext4、启动程序、设备树、内核与 initrd、完整 SquashFS 解压、gzip 解压后的字节数和哈希。它使用构建目录中保存的启动产物和基底启动文件作参照，发行时的报告在 `outputs/validation/`。
