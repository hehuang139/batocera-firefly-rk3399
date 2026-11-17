# Firefly RK3399 eMMC 设备树

目标为原版 Firefly-RK3399 DDR3 开发板，基于已交付的 Batocera 40 / Linux 6.6.27 TF 版设备树。eMMC 专用叠加文件直接包含原 TF 源码，保留 HDMI 音频、USB hub 复位、FUSB302、AP6356S 蓝牙、SDIO Wi-Fi 和 70/75/95°C 温控。

仅改变六个编译后属性：

1. `/mmc@fe330000/status` 从 disabled 改为 okay。
2. `/syscon@ff770000/phy@f780/status` 从 disabled 改为 okay。
3. 删除 `mmc-hs400-1_8v`。
4. 删除 `mmc-hs400-enhanced-strobe`。
5. 增加 `mmc-hs200-1_8v`，使用 HS200 1.8 V。
6. 增加 `max-frequency = <200000000>`。

原版设备树的 8 位总线、non-removable、时钟、PHY、PMIC及电源拓扑保持不变。本首版不启用 HS400，eMMC 介质的实际协商模式在上板后由内核决定。TF 控制器继续启用，便于作为额外存储。

## 根设备与编号

Linux DTS 已固定 `mmc0=&sdio0`、`mmc1=&sdmmc`、`mmc2=&sdhci`。本 eMMC 镜像的 extlinux 参数应使用 **`dev=/dev/mmcblk2p1`**，不同时设置 `label=`。Linux 6.6.27 的 `drivers/mmc/core/host.c` 使用设备树 MMC alias 作为 host index；`drivers/mmc/core/block.c` 用该 index 生成 mmcblk 名称，即便拔掉 TF 卡，eMMC 仍是 mmcblk2。

U-Boot 自己的编号不同：其原版板配置为 eMMC=mmc0、TF=mmc1。内核参数不能照抄 U-Boot 的 mmc0 编号。

来源和 SHA256 固定在 `inputs.json`；MMC 驱动原文在共享目录 `source/docs/integration-evidence/`。实际基底内核的 MMC_BLOCK、SDHCI、SDHCI_OF_ARASAN、PHY_ROCKCHIP_EMMC 均内建 `=y`，不依赖 initrd 额外加载模块。

## 构建与验证

在完整项目根目录运行：

```sh
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD:/project" -w /project firefly-rk3399-fullbuilder:20261108 \
  bash source/emmc/kernel/build-dtb.sh

docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$PWD:/project" -w /project firefly-rk3399-fullbuilder:20261108 \
  python3 source/emmc/kernel/check-reproducibility.py
```

输出到 `work/emmc/kernel/`；原 TF 构建目录和已交付文件不改变。默认 DTB 名称 `rk3399-firefly-batocera-emmc.dtb`。

实际检查结果：39/39 通过；验证 SD 参照 DTB 哈希、两份 DTB 所有属性的差异、eMMC 8 位/1.8 V/PHY/时钟关联、启动驱动内建、固定根设备编号；第二次从源码重建 DTB 哈希一致，10 类编译警告与 SD 版相同。报告 `validation.json` 和 `reproducibility.json`。

eMMC DTB SHA256：`136f55b02480b046bb1d76f6757a46614bb81e5c975ee25ba273062e0a199598`。

文件级验证完成，实际 eMMC 启动、协商速度与重启由首次刷写后检查。
