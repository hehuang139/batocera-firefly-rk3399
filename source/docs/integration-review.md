# Firefly RK3399 镜像集成审查

审核对象：`source/make-image.py`、`source/rootfs/apply.py`、用户态 overlay、extlinux 启动配置及官方基底的启动脚本。以下验证使用实际 Batocera 40 RK3399 镜像中的 initrd、IKCONFIG 与用户态原文，以及 Linux v6.6.27 的 MMC 源码。

## TF 根设备与其他磁盘

extlinux 使用 `dev=/dev/mmcblk1p1`，不传 `label=BATOCERA`。这样即使 USB 上另接一个标签也为 BATOCERA 的盘，TF 固件仍挂载板载 TF 插槽的第一分区。

依据：

- `integration-evidence/init` 从官方基底 `boot/initrd.lz4` 解压提取。SHA256 为 `48c3090a2809b009ca7752d3326369c6a6eb31a3574d2d0507d83afbc57b5dc8`，与 Batocera 40 源码 `package/batocera/boot/batocera-initramfs/init` 完全一致。
- 该脚本第 17 行解析 `dev=`，第 26 行选择该设备。第 27 行的 `label=` 会覆盖此前 `dev=`，因此不能同时保留两项。
- Firefly Linux DTS 的 aliases 第 20 行固定 `mmc1 = &sdmmc`。最终 DTB 读取结果为 `/aliases/mmc1 = /mmc@fe320000`；该节点是 TF 控制器，eMMC 控制器 `/mmc@fe330000` 在本版关闭。
- Linux v6.6.27 `drivers/mmc/core/host.c` 第 535–549 行以 `of_alias_get_id(..., "mmc")` 设置 `host->index`。`drivers/mmc/core/block.c` 第 2538 行以此 index 组成 `mmcblk%u` 名称，因此 TF 对应 `mmcblk1`。对应源码原文保存于 `integration-evidence/mmc-host-6.6.27.c` 和 `mmc-block-6.6.27.c`，来源为 gregkh/linux 的 `v6.6.27` 标签。
- 实际运行 init 中的参数解析片段：仅 `dev=/dev/mmcblk1p1` 得到该设备；同时传 label 则得到 `LABEL=BATOCERA`。结果见 `integration-evidence/validation.json`。

Batocera 的 `batocera-part` 从实际 `/boot` 挂载点推导同盘的第二分区；`S02resize` 对该 SHARE 分区扩容，并会格式化首次镜像的 256 MB 分区。固定 TF 根设备也固定了此操作的目标盘。

## 内核、initrd 与板型

- `LINUX /boot/linux` 和 `INITRD /boot/initrd.lz4` 对应基底原文件；明确的 INITRD 指令由 U-Boot 加载 ramdisk，Linux 无需再使用命令行中的 `initrd=` 文件名。
- 实际 IKCONFIG 中 `CONFIG_BLK_DEV_INITRD=y`、`CONFIG_RD_LZ4=y`、`CONFIG_MMC_DW=y`、`CONFIG_MMC_DW_ROCKCHIP=y`、`CONFIG_MMC_BLOCK=y`，TF 驱动内建，不依赖先挂载 rootfs 才能加载模块。
- Linux DT 型号为 `Firefly-RK3399 Board`，`batocera-settings-get-master` 将其映射为 `Firefly_RK3399_Board`，与新增 `batocera.conf.Firefly_RK3399_Board` 文件名一致。默认 HDMI 输出名称沿用同 RK3399 基底的 HDMI 声卡规则。
- FAT 的 `boot/batocera.board` 是 `firefly-rk3399`；系统架构文件 `usr/share/batocera/batocera.arch` 保持 `rk3399`，模拟器架构不变。
- RK3399 通用启动脚本中的 RG552 内屏检测和 RockPro64 小核下线不应用到 Firefly。蓝牙保留 BlueZ 服务，但不再对已由内核 serdev 接管的 UART0 执行 hciattach。

## 用户态变更与写入范围

- `apply.py` 在写入前核验全部已知原文 SHA256；每个目标路径先解析并确认仍位于提取 rootfs 内，写入时再次检查。外部叶节点符号链接、外部父目录链接及通过外部目录新增 overlay 文件均被拒绝，合法 rootfs 内部链接仍可使用。
- Firefly 升级拒绝守卫放在脚本 shebang 后、上游 `trap do_clean EXIT` 前。拒绝升级不会删除用户已有的手动升级包、MD5 或状态文件。
- rootfs `datainit/system/batocera.conf` 将 `updates.enabled` 设为 0。实际基底 SHARE 分区没有 `/system/batocera.conf`；首启会从更新后的 datainit 初始化。
- `make-image.py` 只创建新的普通 `.img` 文件，写入启动块、FAT 内容都在该文件内进行；复用官方分区表并检查分区几何、启动组件边界与最终 MBR 字节一致性。元数据 sidecar 也必须为新文件，以独占创建模式写入；既有普通文件和符号链接均不能被覆盖。

独立回归：用户态隔离夹具 18/18 通过；元数据普通文件/外链拒绝覆盖 2/2 通过。报告保存于 `integration-evidence/rootfs-fixed-validation.json` 和 `sidecar-validation.json`。
