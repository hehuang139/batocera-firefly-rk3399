# Firefly RK3399 · Select 热键版

本版为 Batocera 40 eMMC test2，新增每只手柄的 Hotkey 跟随其 Select 映射。使用 ES 原生同步 `inputAction/onfinish`，新配对及重新映射保存后立即生效；启动服务在 SHARE 初始化完成后、ES 启动前处理已有配置。键盘和没有可用 Select 按钮的设备保留原映射。

改动以 Batocera 支持的 `boot/overlay` 保存：16 MiB ext4，无日志，仅包含默认手柄配置、规范化工具及启动服务三个文件。原内核、设备树、eMMC/TF 启动器和 SquashFS 系统负载沿用 test1。`manifest.json` 记录配置来源；`assets/overlay-manifest.json` 记录实际文件系统及每个文件的哈希和权限。

2026-11-08 核对：Batocera 全局最新稳定版为 **43.1**；官方 RockPro64 / RK3399 稳定镜像仍为 **40-20240801**，44 属于开发版。出处为 [发行记录](https://batocera.org/changelog)、[稳定索引](https://updates.batocera.org/installs.txt)。

## 重建

准备 Linux、Docker、约 25 GB 空间，以及本项目已交付的 `batocera40-firefly-rk3399-sd-test1.img.gz`。源码包包含固定版本的启动源码、DTB、原始手柄配置及对应许可。

```sh
docker build -t firefly-rk3399-fullbuilder:20261108 source
bash source/select-hotkey/rebuild.sh \
  "$PWD/outputs/batocera40-firefly-rk3399-sd-test1.img.gz" \
  "$PWD/outputs/rebuilt-select-hotkey"
```

输出目录必须尚不存在。脚本重新构建启动组件与 Select 配置，生成 saved overlay、eMMC 镜像及自带固件的 TF 安装镜像，再执行整盘验证。所有写操作针对普通镜像文件，不写主机磁盘设备。固定 SD 输入的压缩与解压哈希仍由 `source/emmc/inputs.json` 核对。

文件系统时间戳会影响新构建镜像的哈希；使用新输出目录中的 `SHA256SUMS`。主发行包附带 `validation/`，记录实际执行的配置行为、文件系统检查及两份镜像验证结果。

安装方法见 [eMMC安装说明](docs/eMMC安装说明.md)，使用方法见 [Select热键](docs/Select热键.md)。
