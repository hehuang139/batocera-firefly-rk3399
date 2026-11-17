# 43.1 复建

本版以两个固定上游发布包为输入：官方 RockPro64 40 提供 RK3399 6.6.27 模块及固件，官方 N2+ 43.1 提供完整双层 ARM64 用户态和 initramfs。输入的下载地址、大小与 SHA256 分别在 `source/base-manifest.json`、`source/v431/provenance/base-manifest.json`。将它们放到下面示例的位置；哈希不一致会在创建输出前退出。

在解压后的项目根目录执行（Ubuntu / Docker，至少 30 GiB 空间）：

```sh
docker build -f source/v431/Dockerfile -t firefly-rk3399-v431builder:local .
docker run --rm --network none \
  -v "$PWD:/project" -w /project firefly-rk3399-v431builder:local \
  python3 source/v431/rebuild.py \
    downloads/batocera-rk3399-rockpro64-40-20240801.img.gz \
    downloads/v431/boot.tar.xz \
    outputs/rebuilt431 --scratch /project/work/rebuilt431
```

输出和临时目录都必须为新的路径。脚本只操作普通文件：验证输入、提取系统、应用有清单的板级改动、验证全部内容和权限、重打包主系统、组装两种整盘镜像、压缩回读及独立验证。成功后输出 eMMC 镜像、自带固件的 TF 安装卡、SHA256 和验证记录。临时目录较大，完成后可以自行删除。

`inputs.json` 固定实际发布组件；`provenance/final-content.json` 保存主系统全部文件的内容和元数据。复建会恢复时间戳并要求生成的主系统 SHA256 与发行版相同。FAT 时间戳受本次构建时间影响，因此整盘镜像重新生成 SHA256。构建工具版本也会影响 SquashFS 字节，建议使用随包 Dockerfile 中的 Ubuntu 22.04 工具。

U-Boot、内核、设备树的源文件、补丁、工具及复建入口保留在 `source/boot/`、`source/emmc/boot/`、`source/kernel/`、`source/emmc/kernel/`；本入口使用随包提供并经过固定哈希校验的板级产物。

## 从 Git 仓库构建

Git 仓库保存源码及较小的固定板级组件。两个大文件 `assets/rufomaculata`、`assets/share.ext4` 随 Release 的完整 `*-source.tar.gz` 提供。推荐直接解压完整源码包构建；也可以在克隆的 Git 仓库根目录运行：

```sh
python3 source/v431/restore-release-assets.py /路径/batocera431-firefly-rk3399-source.tar.gz
```

恢复脚本只提取这两个固定文件，并核对 `inputs.json` 的大小和 SHA256，然后再按上文下载两份官方输入并执行 Docker 构建。
