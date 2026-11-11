# Android 模拟器配置插件

本插件在本地及适合 Docker 的环境中，通过配置文件创建 Android Virtual Device 并启动模拟器。

可以直接要求为 Android 运行或测试准备、启动模拟器，或查看状态和屏幕，无需指定配置文件或安装脚本。skill 检查设备和 API 要求，优先复用合适的模拟器或 AVD，再考虑新建。仅编辑 Android 代码不需要准备模拟器，状态查询保持只读。

## 使用项目的独立性

SDK 和 AVD 准备留在操作者环境。使用插件的项目保留标准 Android 工具要求和测试命令，不依赖 AI 插件安装或私有配置；正常 Android 构建插件仍受支持。

## 包含的工具

- 安装 Android SDK 命令行工具并接受许可证。
- 根据手机、平板、桌面、TV 和手表配置创建 AVD。
- 使用感知架构的默认值启动模拟器。
- 通过模拟命令执行冒烟测试，不启动真实模拟器。

这些脚本需要 Bash 4.3+ 和 GNU 兼容 Shell 工具。从已安装插件根目录定位绝对路径；随包配置是字面数据。SDK 安装器在项目目录外下载，遵循现有 SDK 归属，将被替换工具保存在 `cmdline-tools/previous.*` 目录。随包命令行工具版本是最低环境选择，不保证始终下载最新上游版本；已安装的更新工具会被复用。

除非配置明确覆盖，启动时保留已有 `DISPLAY`。AVD 启动 guard 或原生锁被占用或处于中断状态时拒绝启动；关闭只针对自己启动的进程。手动恢复锁前，确认所有管理者已停止。新 AVD 可在首次启动前设置分区大小；调整已有或自定义 userdata 需要显式设置 `EMULATOR_ALLOW_DATA_WIPE=true`。此设置授权破坏性重置该 AVD，不应作为日常默认值。

普通设备管理请参考当前 [Android CLI 指引](https://developer.android.com/studio/run/emulator-commandline)。随包脚本继续用于配置文件流程；核对已安装模拟器的参数，不假定每个 SDK 版本都支持相同选项。

## Android Emulators 状态面板

在支持 MCP Apps 的宿主应用全局侧栏或对话标签页打开 **Android Emulators**，或调用 `android_emulator_status`。只读面板列出已配置 AVD 和已连接模拟器，包括启动就绪状态、序列号、Android 和 API 版本、ABI、配置内存及分辨率。支持过滤、手动刷新，以及可见时每十秒自动刷新。探测失败保持未知或不可用。未观察到 ADB 连接的已配置 AVD 标记为断开连接，不代表其进程已停止。

已启动的模拟器可使用 **Capture screen**。每次点击以明确序列号调用仅供应用使用的 `android_emulator_screenshot`，通过 `adb exec-out screencap -p` 捕获一张 PNG。刷新不会截屏，不在设备保存截图，也拒绝真实手机。关闭预览即丢弃显示图像。面板不会启动、停止、重置或解锁模拟器。

安装 [uv](https://docs.astral.sh/uv/)，让 ADB 在 MCP 服务所在环境可用。兼容宿主应用会根据清单自动注册本地 stdio 服务：

```bash
uv run --script scripts/status-server.py
# 宿主应用无法呈现 MCP Apps 时使用 JSON：
python3 scripts/emulator_status.py
```

ADB 查找依次考虑 `ANDROID_ADB_COMMAND`、PATH、`ANDROID_HOME`、`ANDROID_SDK_ROOT` 和 `~/android-sdk`。常用 ADB 服务环境变量仍可用；调用 ADB 可能启动本地服务。AVD 清单优先使用 `ANDROID_AVD_HOME` 或 `ANDROID_USER_HOME`，回退到 `~/.android/avd`。只读取已有 `.ini`，不执行配置文件或重写配置。TCP 连接的模拟器通过 Android QEMU 属性识别；离线 TCP 设备无法确认为模拟器。未匹配或离线的模拟器实例会阻止将未知本地 AVD 报告为断开连接。

原生呈现要求支持 MCP Apps 和 OpenAI 对话入口。这是本地 MCP 服务，不是已部署的远程 ChatGPT 应用。共享 UI 构建与验证见仓库中的 `scripts/android-status/README.md`。

## 插件打包

`plugin.json` 是可移植元数据的权威来源。客户端清单与完整 skill 资源会生成到 `me.claude` 和 `me.codex`，请从这两个仓库安装。源 skill 使用可移植的 frontmatter。Claude 路由按 skill 目录保存在 `extensions.com.anthropic.claude.skillFrontmatter` 中，仅注入生成的 Claude skill。Codex 的 skill 文件保持源文件原样复制。

## 改进反馈

插件问题向 [storytellerF/me issues](https://github.com/storytellerF/me/issues) 反馈。报告前，skill 要求检索已打开和已关闭的 issue，使用脱敏或合成示例，并遵循用户已有的发布授权。优先复用已有报告；无法访问时，保留尚未提交的草稿。

## Python 配置控制器

在 Windows 或 Unix 上，可通过 Python 3.10+ 直接运行 `python /absolute/plugin/scripts/start-avd.py /absolute/profile`。Shell 启动入口只选择解释器并转发参数（`ANDROID_PROFILE_PYTHON` 可覆盖自动查找）。SDK 安装仍由 Bash 编排，其兼容工具使用同一套 Python 配置解析器、工具解析器和参数映射器。原生启动控制器负责更新 AVD 配置。

配置文件始终是字面数据。原生 Windows 批处理工具拒绝命令元字符，以及无法安全转发的以反斜杠结尾的参数；可执行工具接收参数列表。使用 Ctrl+C 或 Windows 原生 Ctrl+Break 平滑取消。Git Bash 的 `kill -TERM` 会强制终止原生 Windows 程序，无法执行 Python 清理；恢复前检查遗留的 guard。

配置直接从文件读取，保留键和选项的大小写。AVD 名称、自定义路径、模拟器选项、INI 覆盖值和擦除权限不继承环境变量，应写入配置文件。Shell 创建入口将配置值保存在独立映射中，不导出为环境变量。只为 Android 工具显式转发 `ANDROID_HOME`、`ANDROID_AVD_HOME`、`ANDROID_USER_HOME`，以及 `EMULATOR_DISPLAY` 到 `DISPLAY` 的映射。宿主机 PATH、HOME、配置文件及解释器选择仍使用环境变量。

即使命令根进程先退出，启动控制器也会保持配置 guard，直到其管理的整棵命令进程树停止。清理失败时保留 guard，恢复前检查归属进程。Windows 脚本工具通过 Git Bash 使用其 shebang 解释器。Unix 设备工作进程必须留在原进程组；脱离的会话不在启动器管理范围内。

在 Windows 上，共享工具环境边界在启动原生工具前，将继承和配置文件中的 `ANDROID_HOME`、`ANDROID_AVD_HOME`、`ANDROID_USER_HOME` 从 Git Bash 路径转换为原生路径，使工具与配置查找使用相同目录。空值保持为空。

Git Bash 路径转换输出按 UTF-8 读取，不受 Windows ANSI 代码页影响，保证 Unicode SDK 和 AVD 目录名完整。

## 开发

离线回归套件及源码检出前提见[仓库开发文档](../../DEVELOPMENT.md#shell-边界回归测试)。
