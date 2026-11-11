# PvgTimingFix

此独立 Lilu 插件发布 AppleParavirtFramebuffer 已有的固定频率详细时序，避免虚拟机调度抖动成为 CoreVideo 使用的标称显示周期。它不实现视频解码，也不替换应用呈现命令。

随包 `PvgTimingFix` 是已验证的 x86-64 Mach-O kext 包。`artifact.json` 记录校验和、源文件及依赖修订。驱动只路由 Darwin 24 上审计过的 52 字节方法，不触碰其他方法。打包要求 macOS 15.8.1 构建 **24H32** 和 Lilu **1.7.2**。其他版本、显示模式变化及睡眠恢复未验证。`-pvgtimingoff` 禁用插件。

固件、私有凭据和虚拟机状态留在使用插件的项目外。通过插件 `prepare-macos-gpu-boot.py` 准备操作者自有 OpenCore 镜像的新副本，见插件 README。不修改系统卷或提供的原始固件。

贡献者重建和验证见插件 DEVELOPMENT.md。Lilu 适用的源码和二进制再分发条款保留在 `LICENSE-Lilu.txt`，新增时序钩子按 `LICENSE` 分发。
