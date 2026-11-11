---
name: android-emulator-profile
description: Android 运行或测试需要准备、启动模拟器，配置 AVD 或 SDK 前提条件，或查看模拟器状态与屏幕预览时使用。在内部选择已有设备和配置，不因编辑 Android 代码就创建模拟器。
---

# Android 模拟器配置

## 选择环境

执行 Android 运行或测试时，先检查用户要求的 API 级别、设备类型和现有模拟器。复用合适的运行中模拟器，或启动匹配的已有 AVD；仅在需要时准备 SDK 工具、系统镜像和新配置。用户不必点名配置文件或辅助脚本。状态或屏幕查看保持只读。模拟器就绪后，执行项目正常的运行或测试流程；模拟器就绪本身不代表测试通过。

## 使用项目的独立性

在操作者环境中准备 SDK、AVD 并定位本 AI 插件的辅助工具。不能仅为准备模拟器，就将其安装路径、私有配置或启动命令写入项目构建、CI 或文档。项目可以声明标准 SDK、AVD 要求并使用普通 adb 和测试命令；Android Gradle 插件和必需测试库仍是正常依赖。明确要求集成 AI 插件时，只处理用户指定的范围。

## 随包路径

以下路径相对于插件根目录：

- `scripts/install-sdk.sh`
- `scripts/accept-sdk-licenses.sh`
- `scripts/create-avd.sh`
- `scripts/start-avd.sh`
- `scripts/profile-utils.sh`
- `tests/test-start-avd-docker.py`
- `tests/test-install-sdk.py`
- `profiles/mobile.profile`
- `profiles/watch.profile`
- `profiles/tablet.profile`
- `profiles/desktop.profile`
- `profiles/tv.profile`

## 工作流程

安装或更新 Android SDK 工具：

```bash
ANDROID_HOME=${ANDROID_HOME:-$HOME/android-sdk} ./scripts/install-sdk.sh
```

创建指定配置的 AVD：

```bash
./scripts/create-avd.sh ./profiles/mobile.profile
```

启动指定配置的模拟器：

```bash
./scripts/start-avd.sh ./profiles/mobile.profile
```

在 `me` 源码检出目录内，从此插件目录运行模拟命令回归套件（依赖仓库测试辅助工具）：

```bash
python tests/test-start-avd-docker.py
```

## 配置规则

- 使用非默认配置时，将配置路径作为第一个参数。
- 未传配置路径时，`create-avd.sh` 和 `start-avd.sh` 使用 `${ANDROID_PROFILE:-${ANDROID_PROFILE_DIR:-$HOME/android-profiles}/mobile.profile}`。
- 根据[官方命令行参考](https://developer.android.com/studio/run/emulator-commandline)核对已安装工具的选项。日常管理可使用当前可用的 Android CLI；随包脚本实现显式配置文件流程。不要假定参数可以原样用于其他启动器。
- `SYS_IMG_PKG` 必须是未带 ABI 后缀的 Android 系统镜像包前缀。
- 脚本按运行架构追加 ABI：`x86_64` 使用 `x86_64`，`aarch64`/`arm64` 使用 `arm64-v8a`；不支持的架构在创建前失败。
- 配置文件不得定义 `ARCH`、`ABI`、`AVD_ARCH`、`AVD_ABI`、`AVDMANAGER_ABI`、`AVDMANAGER_ARCH`、`EMULATOR_ABI` 或 `EMULATOR_ARCH`。
- 配置文件是字面数据，可带匹配的外层引号，不能作为 Shell 程序执行。
- 竞争操作期间保留 AVD 启动 guard 和原生锁。恢复前检查中断的 guard 或锁。只停止自己管理的模拟器进程。
- 新 AVD 在首次生成 userdata 镜像前设置分区大小。调整已有或自定义 userdata 大小需要显式设置 `EMULATOR_ALLOW_DATA_WIPE=true`；未获准擦除该 AVD 数据时，不得启用。

## 使用说明

- 从本 skill 位置定位已安装插件根目录，使用脚本和配置文件的绝对路径。保持目标项目工作目录不变。
- SDK 下载和模拟器启动应已包含在用户请求或既有授权中；只有缺少相应范围时才询问。已授权操作不重复申请。
- `test-start-avd-docker.py` 使用模拟的 `emulator` 和 `adb` 命令，不启动 Docker 或真实模拟器。
- 区分宿主机 ADB 服务（5037）与所选模拟器的 ADB 端点（通常为 5555，但以其控制台和 ADB 端口对为准）。先核对虚拟机路由；gvproxy 的宿主机别名可以访问宿主机回环地址。仅在网络确有需要时添加限定范围的端口代理或防火墙规则，不盲目重启共享代理服务。

## 只读状态与屏幕预览

调用 `android_emulator_status`，从全局侧栏或对话旁打开 **Android Emulators** 面板。它读取已配置 AVD、ADB 连接和启动就绪状态，不启动或重置设备。MCP Apps 不可用时，用 Python 3 运行 `scripts/emulator_status.py`，概述 JSON 快照。

截屏由面板显式操作触发，使用仅供应用调用的 `android_emulator_screenshot` 工具。不要添加自动截屏轮询。缺少 ADB 连接表示不可用或未知，不能证明全部 AVD 已停止。其他清单目录通过 `ANDROID_AVD_HOME` 指定，明确的 ADB 可执行文件通过 `ANDROID_ADB_COMMAND` 指定；完整查找规则见所属 README。

## Python 配置控制器

在 Windows 或 Unix 上，可通过 Python 3.10+ 直接运行 `python /absolute/plugin/scripts/start-avd.py /absolute/profile`。Shell 启动入口只选择解释器并转发参数（`ANDROID_PROFILE_PYTHON` 可覆盖自动查找）。SDK 安装仍由 Bash 编排，其兼容工具使用同一套 Python 配置解析器、工具解析器和参数映射器。原生启动控制器负责更新 AVD 配置。

配置文件始终是字面数据。原生 Windows 批处理工具拒绝命令元字符，以及无法安全转发的以反斜杠结尾的参数；可执行工具接收参数列表。使用 Ctrl+C 或 Windows 原生 Ctrl+Break 平滑取消。Git Bash 的 `kill -TERM` 会强制终止原生 Windows 程序，无法执行 Python 清理；恢复前检查遗留的 guard。

配置直接从文件读取，保留键和选项的大小写。AVD 名称、自定义路径、模拟器选项、INI 覆盖值和擦除权限不继承环境变量，应写入配置文件。Shell 创建入口将配置值保存在独立映射中，不导出为环境变量。只为 Android 工具显式转发 `ANDROID_HOME`、`ANDROID_AVD_HOME`、`ANDROID_USER_HOME`，以及 `EMULATOR_DISPLAY` 到 `DISPLAY` 的映射。宿主机 PATH、HOME、配置文件及解释器选择仍使用环境变量。

即使命令根进程先退出，启动控制器也会保持配置 guard，直到其管理的整棵命令进程树停止。清理失败时保留 guard，恢复前检查归属进程。Windows 脚本工具通过 Git Bash 使用其 shebang 解释器。Unix 设备工作进程必须留在原进程组；脱离的会话不在启动器管理范围内。

在 Windows 上，共享工具环境边界在启动原生工具前，将继承和配置文件中的 `ANDROID_HOME`、`ANDROID_AVD_HOME`、`ANDROID_USER_HOME` 从 Git Bash 路径转换为原生路径，使工具与配置查找使用相同目录。空值保持为空。

Git Bash 路径转换输出按 UTF-8 读取，不受 Windows ANSI 代码页影响，保证 Unicode SDK 和 AVD 目录名完整。

## 上游改进反馈

- 发现有明确改进方向的插件缺陷或可复用的改进建议时，向 [storytellerF/me](https://github.com/storytellerF/me/issues) 反馈，并注明插件和 skill。若问题仅属于当前项目，且没有插件缺陷的证据，则不在此范围内。先完成主要任务，再处理不影响当前工作的反馈。
- 搜索或发布之前，将证据整理为不含隐私的最小摘要或合成复现案例。不得泄露原始对话、私有代码、日志、截图、凭据、个人或账户信息，以及私有路径和 URL。如果无法安全披露，就只在本地保留发现。
- 搜索已打开和已关闭的 issue，阅读可能匹配的报告及其解决方案。优先复用已有报告；如果是不同的回归问题或尚未覆盖的场景，可另建 issue 并关联原报告。发布新 issue 或有实质帮助的评论必须已经获得用户授权；本规则本身不授予发布权限。未获授权时，准备一份尚未提交的草稿。
- 反馈应包含插件和 skill 版本、实际与预期行为、复现步骤或建议，以及重复报告的检索结果。新 issue 的标题应以插件名开头。访问或提交失败时，保留草稿并说明阻碍。提交结果不确定时，先确认是否已成功，再考虑重试。返回报告链接，或明确标注草稿尚未提交。
