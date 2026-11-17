# 重建 eMMC 镜像与 TF 安装卡

依赖 Linux、Docker 和约 25 GB 空间，使用项目根目录的 `source/Dockerfile`：

```sh
docker build -t firefly-rk3399-fullbuilder:20261108 source
```

将本项目已交付的 `batocera40-firefly-rk3399-sd-test1.img.gz` 放进当前项目的 `downloads/` 目录；`source/emmc/inputs.json` 固定其压缩/解压 SHA256，及沿用的 kernel、initrd、SquashFS 与 SHARE 哈希。

在项目根目录执行，下列输出目录必须尚不存在：

```sh
bash source/emmc/rebuild.sh \
  "$PWD/downloads/batocera40-firefly-rk3399-sd-test1.img.gz" \
  "$PWD/outputs/rebuilt-emmc"
```

流程：

1. 校验 TF 发行镜像，自编 DDR3 eMMC TPL/SPL、U-Boot、TF-A 及 Linux 设备树。
2. 从 TF 发行镜像复制已验证的系统负载；更换 eMMC 引导、DTB、根设备参数及说明，清零 FAT 空闲簇。
3. 压缩 eMMC 镜像并校验解压结果，生成板上安装程序使用的 `manifest.json`。
4. 另建 TF 安装镜像，保留 TF 启动器，启用 eMMC，并放入完整 eMMC 压缩镜像、manifest 与安装脚本。
5. 生成 SHA256SUMS，对两份成品分别运行独立整盘验证。

安装程序 `flash/install-to-emmc.py` 只能在原版板子的 TF 安装环境中使用。重建工具只写普通 `.img` 文件，不写电脑磁盘。启动固件使用固定源码包和配置；工具链与 FAT 时间戳会影响整盘哈希，重建输出使用自己的校验文件。

发行源码归档同时保留上一个 TF 版的来源、许可、构建脚本，新增 eMMC 部分在 `source/emmc/`。原始官方 Batocera 40 系统与原 TF 板级变更的来源见 `source/docs/BUILD.md`。
