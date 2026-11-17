# Firefly RK3399 · Select 手柄热键

本版将手柄 Hotkey 设为该手柄自己的 **Select**，不固定按钮编号。有些手柄将这颗按键标为 Back 或 View。

- **Select + Start：退出游戏，返回游戏列表。**
- 其他原有 Hotkey 组合改用 Select 作为组合键，具体功能取决于模拟器。
- 第一次配置手柄时，将 Select 项绑定到你要使用的 Select / Back / View 键；Hotkey 步骤也可以按同一颗键。配置保存后，系统会让 Hotkey 跟随 Select。
- 更换手柄、蓝牙重新配对或重新映射后仍按各自的 Select 设置。
- 键盘配置以及没有 Select 映射的设备保留原设置。

系统版本为 Batocera 40。2026-11-08 核对官方发布信息：全局最新稳定版为 43.1，RockPro64 / RK3399 官方稳定镜像仍为 40-20240801。此移植沿用该平台稳定基底。

官方信息：

- https://batocera.org/changelog
- https://updates.batocera.org/installs.txt

本版启动时会读取 `boot/overlay` 中的持久配置。保留该文件即可在每次启动后继续使用 Select 热键。
