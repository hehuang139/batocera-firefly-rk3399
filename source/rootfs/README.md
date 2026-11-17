# Firefly RK3399 用户态适配

基于 Batocera 40 `f7dabcebc82ed66fb740727d64913e2e86fc1d6e`。
`upstream/` 保存待改文件原文，`provenance.json` 记录上游路径和 SHA256；
应用器先核验所有文件，再写入，遇到不同基底会停止。
目标及父目录中的符号链接必须解析到 rootfs 内，越界链接会被拒绝。

```sh
python3 source/rootfs/apply.py work/base-rootfs --check
python3 source/rootfs/apply.py work/base-rootfs --report logs/rootfs-adaptation.json
```

改动：

- `S02fan` 按 `pwmfan` 设备名识别风扇，不依赖易变的 `hwmon0` 编号。
- `S33checkhdmi` 仅在 RG552 上启动其 GPIO 54 内屏检测，Firefly 不启动这一线程。
- 为 `Firefly-RK3399 Board` 增加 HDMI 音频默认输出。
- Firefly 蓝牙由设备树描述的 UART serdev 驱动管理；保留 BlueZ 服务，跳过旧的 `hciattach` 和盲目 `rfkill0` 重置。
- 默认关闭在线更新检查，在线升级脚本识别 Firefly 板型并停止，避免通用升级覆盖本移植的设备树和启动配置。
  拒绝逻辑位于原脚本的清理 trap 和任何升级操作之前，会保留用户已下载的手动升级包。

镜像打包器还应将 FAT 分区 `boot/batocera.board` 设为 `firefly-rk3399`，
并将 SHARE 分区已有 `system/batocera.conf` 的 `updates.enabled` 设为 `0`。
此处不改变模拟器默认配置和 CPU 在线状态。
