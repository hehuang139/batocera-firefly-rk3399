# 清理 FAT32 空闲簇

`mcopy` 重写系统文件后，原文件占用过的簇会成为空闲簇，但里面的旧字节仍保留，导致整盘 gzip 无法有效压缩。`zero-free-fat.py` 只将 FAT 表标记为空闲的数据簇填零，不改变文件系统分配。

```sh
# 只读检查分区几何、双 FAT 一致性、可清理空间
python3 source/zero-free-fat.py output.img --check-only

# 清零、fsync，再核对全部受保护字节与全部空闲簇
python3 source/zero-free-fat.py output.img

# 只读检查所有空闲簇已经为零
python3 source/zero-free-fat.py output.img --verify

# 稀疏镜像夹具回归
python3 source/test-zero-free-fat.py
```

工具只接受现有普通 `.img` 文件，不接受符号链接或设备节点，并使用文件锁避免本工具并发写入。只支持本镜像的已知 MBR/FAT32 几何，校验两份 FAT 完全一致后，遍历有效簇 `2..data_clusters+1`，忽略 FAT 尾部未使用条目。写入合并后的连续空闲区间，范围始终限制在 BPB 声明的数据区内。

写入前后分别对所有**非空闲簇范围**计算 SHA256，覆盖 MBR、启动程序、FAT 元数据、已分配文件数据、分区尾部填充和整个 SHARE。两次摘要必须一致；随后逐块检查空闲簇全零。镜像目录结构、FAT 分配、文件大小和 SHARE 内容都保持原值。文件写入与镜像压缩应顺序执行。

夹具使用与成品相同的稀疏镜像尺寸和分区几何，设置四个非零空闲簇（含连续簇与最后一个合法簇）、已分配数据和 SHARE/尾部哨兵。19 项检查通过，含 FAT 不一致预检拒绝、越界尾条目排除和符号链接/设备拒绝。结果见 `zero-free-fat-validation.json`。

实际成品首次只读检查识别 3 段空闲区，共 `2363043840` 字节。清理结果仍需以每次工具输出及最终镜像验证报告为准。
