---
name: android-profile
description: 使用随附的 Android SDK 和 AVD 配置脚本安装 Android SDK 工具、创建 Android 虚拟设备、启动适合 Docker 的模拟器，并运行 start-avd 冒烟测试。
---

# Android Profile

当任务涉及此插件的 Android SDK、AVD、模拟器或 Docker 冒烟测试脚本时，使用此技能。

## 随附路径

按此插件根目录解析路径：

- `scripts/install-sdk.sh`
- `scripts/accept-sdk-licenses.sh`
- `scripts/create-avd.sh`
- `scripts/start-avd.sh`
- `scripts/profile-utils.sh`
- `tests/test-start-avd-docker.sh`
- `profiles/mobile.profile`
- `profiles/watch.profile`
- `profiles/tablet.profile`
- `profiles/desktop.profile`
- `profiles/tv.profile`

## 工作流

安装或更新 Android SDK 工具：

```bash
ANDROID_HOME=${ANDROID_HOME:-$HOME/android-sdk} ./scripts/install-sdk.sh
```

创建已配置的 AVD：

```bash
./scripts/create-avd.sh ./profiles/mobile.profile
```

启动已配置的模拟器：

```bash
./scripts/start-avd.sh ./profiles/mobile.profile
```

从仓库根目录运行假命令冒烟测试：

```bash
tests/test-start-avd-docker.sh
```

## 配置规则

- 使用非默认配置时，将配置路径作为第一个参数传入。
- 如果未传入配置路径，`create-avd.sh` 和 `start-avd.sh` 会使用 `${ANDROID_PROFILE:-${ANDROID_PROFILE_DIR:-$HOME/android-profiles}/mobile.profile}`。
- 添加或检查 `EMULATOR_FLAG_*` 和 `EMULATOR_VALUE_*` 条目时，使用官方模拟器命令行参考：https://developer.android.google.cn/studio/run/emulator-commandline
- `SYS_IMG_PKG` 必须是 Android 系统镜像包前缀，不包含 ABI 后缀。
- 脚本会根据运行时架构追加 ABI：`x86_64` 使用 `x86_64`，`aarch64` 使用 `arm64-v8a`。
- 不要在配置文件中定义 `ARCH`、`ABI`、`AVD_ARCH`、`AVD_ABI`、`AVDMANAGER_ABI`、`AVDMANAGER_ARCH`、`EMULATOR_ABI` 或 `EMULATOR_ARCH`。

## Codex 注意事项

- 优先从插件根目录运行脚本，这样相对路径可以自然工作。
- 运行会下载 SDK 包或启动长期运行模拟器进程的工作流前，先询问用户。
- `test-start-avd-docker.sh` 使用假的 `emulator` 和 `adb` 命令；它不会启动 Docker 或真实模拟器。
- 如果模拟器在宿主机上、虚拟机需要访问宿主机 ADB 端口，提示用户在宿主机设置 `netsh interface portproxy` 端口转发，并添加允许虚拟机网段访问 `5555` 端口的防火墙规则。
