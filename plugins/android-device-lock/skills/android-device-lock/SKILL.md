---
name: android-device-lock
description: 在共享 Android 真机或模拟器上运行测试、准备测试会话，或检查设备占用与租约归属时使用。适用于不同测试框架；不包括仅在宿主机运行的 JVM 测试，以及只读模拟器清单和屏幕预览。
---

# Android 设备锁

任何需要独占访问的 Android 设备测试都使用本插件，包括 UI、instrumentation、端到端和 adb 驱动测试。锁流程不受测试框架影响。

## 独立于项目执行

插件在目标项目之外管理设备访问。通过已安装插件获取锁，从项目原工作目录执行其现有测试命令，命令保持不变，最后释放锁。已有 adb、Gradle 或 Android 插件及测试框架依赖仍是普通项目要求，与本 AI 插件不同。

- 根据已加载 skill 位置定位插件根目录：本文件位于 `<plugin-root>/skills/android-device-lock/SKILL.md`。使用 `<plugin-root>/scripts/adb-device-lock.sh` 的绝对路径；不要假定项目包含 `plugins/` 目录。
- 不将锁辅助工具复制、内置、生成或重新实现在目标项目中。不要仅为使用插件就添加锁依赖、测试包装器、构建修改、CI 配置或项目文档。项目集成需要用户另行明确要求。
- 归属令牌文件和临时编排放在项目外的系统临时目录。`project_dir` 和 `test_name` 只标识租约归属，不配置项目，也不选择独立的锁。
- 使用同一 adb 设备的所有项目，必须使用相同的设备端锁路径。使用随包默认路径。已有非默认路径必须由所有参与者和状态收集器共同使用，不能每个项目各选一条。
- 找不到已安装辅助工具时，报告插件资源不可用，不向项目复制或自行替代实现。

## 必需行为

- 启动设备测试会话、安装或运行应用，以及修改设备状态之前，先获取设备锁。
- 锁保存在真机或模拟器上，不能只放在宿主机。
- 使用随包工具的设备端修改 guard 和原子租约目录。过期接管、释放及续租必须位于 guard 内；读取令牌后无保护地删除，可能误删后继任务的租约。所有参与者使用相同版本和路径的工具。元数据通过重命名发布。
- 锁元数据至少包含 `project_dir`、`test_name`、`requested_at_utc`、`acquired_at_utc`、`max_timeout_seconds`、`expires_at_epoch`、`host`、`pid` 和 `owner_token`。
- 已有有效锁时，轮询等待其释放或过期。
- 锁过期时，移除旧锁并获取新锁。
- 始终在 trap 或 finally 中释放锁，且仅当归属令牌匹配时释放。

## 快速开始

在目标项目目录运行。此处 `DEVICE_LOCK_PLUGIN_ROOT` 是根据已加载 skill 位置解析的会话内绝对路径，不是项目设置：

```bash
"$DEVICE_LOCK_PLUGIN_ROOT/scripts/adb-device-lock.sh" run \
  --serial "$ANDROID_SERIAL" \
  --project-dir "$PWD" \
  --test-name "android-device-suite" \
  --max-timeout-seconds 1800 \
  --wait-timeout-seconds 3600 \
  -- ./gradlew connectedAndroidTest
```

手动获取、释放和续租请阅读 [`references/manual-lock-lifecycle.md`](references/manual-lock-lifecycle.md)。

## 执行指引

工具处理 Git Bash 调用 Windows ADB 时的路径转换：Android 路径保持不变，本地元数据上传路径在 `cygpath` 可用时进行转换。

- 每个 adb 设备分别加锁。连接多个设备时使用 `--serial`。
- `--max-timeout-seconds` 略长于预计最长测试时间，让遗弃的锁可在过期后恢复。
- `--test-name` 使用具体测试名称，例如 CI 作业名、套件名或本地命令名。
- 默认共享锁路径为 `/data/local/tmp/android-device-test.lock.d`，普通调试设备和模拟器上的 `adb shell` 可写。
- 单个命令无法覆盖全部设备操作时，从 agent 管理的临时 Shell 会话执行手动生命周期，不修改项目测试运行器。

## 失败处理

- `adb` 看不到设备时，在等待锁之前失败。
- 元数据损坏或缺失表示归属未知。工具不会根据目录 mtime 推断过期；恢复前先检查。中断的 `.guard` 目录也应保留，直到确认所有修改操作已停止。
- 租约控制器需要 Python 3.10+ 进行严格 JSON 和类型检查；无法自动查找解释器时设置 `ANDROID_DEVICE_LOCK_PYTHON`。
- 释放时令牌不匹配，不删除锁；它属于其他运行任务。
- `run` 使用固定时长租约，不自动续租。命令必须在租约内结束；更长操作手动续租，无法确认续租时在到期前停止设备工作。自定义路径必须位于 `/data/local/tmp` 下，且不能含父目录跳转。

## 原生 Python 入口

Windows 或 Unix 可使用相同命令和选项运行 `python /absolute/plugin/scripts/adb-device-lock.py`。`.sh` 入口只选择 Python 3.10+ 解释器并转发参数。控制器保留设备 guard 和令牌协议，负责命令取消、子进程清理和租约释放。

## 随包资源

- `scripts/adb-device-lock.sh`：确定性的 adb 锁辅助工具，提供 `acquire`、`release`、`renew` 和 `run` 命令。

## 只读租约状态

查看设备占用、当前归属、任务或到期时间时，调用 `android_device_lock_status`，从全局侧栏或对话旁打开 **Device Leases**。观察无需获取或释放锁。MCP Apps 不可用时，用 Python 3 运行 `scripts/lock_status.py`，概述 JSON 快照。

工具结果和 UI 不得泄露归属令牌。过期元数据表示陈旧租约仍在，不代表面板已经释放设备。离线设备和不可读元数据必须保持未知或不可用。工具没有持久等待队列，不得编造等待任务。自定义锁路径时，`ANDROID_DEVICE_LOCK_PATH` 应与 `--lock-path` 相同。

租约元数据由 `scripts/lock-metadata.py` 使用 JSON 编码的占位值，从随包 `scripts/lock.json.template` 渲染。这两项资源必须与已安装辅助工具一同保留；字段提取和渲染保持严格 JSON 验证。

远程租约删除失败时，`release` 返回非零状态并保留归属令牌供恢复。命令成功但清理失败时，`run` 也返回非零；已有命令失败或信号退出状态保持不变。核对设备连接与归属后，使用保留的令牌重试释放。

## 取消、清理与恢复

Windows 使用 Ctrl+C 或原生 Ctrl+Break 平滑取消。Git Bash `kill -TERM` 强制终止原生 Python，无法执行清理；恢复前检查保留令牌和设备 guard。原生等待在命令运行期间分派信号，再停止自有命令树，最后释放。

`run` 在释放租约前停止剩余后代，即使命令根进程已退出。Windows 使用 Job Object；Unix 命令必须将设备 worker 留在自有进程组，不得 daemonize 或创建脱离会话。无法确认进程树清理时，保留租约和归属令牌供恢复。Windows shebang 入口通过 Git Bash 使用声明的解释器和原参数，该解释器必须在 Git Bash 环境可用。

## 上游改进反馈

- 发现有明确改进方向的插件缺陷或可复用的改进建议时，向 [storytellerF/me](https://github.com/storytellerF/me/issues) 反馈，并注明插件和 skill。若问题仅属于当前项目，且没有插件缺陷的证据，则不在此范围内。先完成主要任务，再处理不影响当前工作的反馈。
- 搜索或发布之前，将证据整理为不含隐私的最小摘要或合成复现案例。不得泄露原始对话、私有代码、日志、截图、凭据、个人或账户信息，以及私有路径和 URL。如果无法安全披露，就只在本地保留发现。
- 搜索已打开和已关闭的 issue，阅读可能匹配的报告及其解决方案。优先复用已有报告；如果是不同的回归问题或尚未覆盖的场景，可另建 issue 并关联原报告。发布新 issue 或有实质帮助的评论必须已经获得用户授权；本规则本身不授予发布权限。未获授权时，准备一份尚未提交的草稿。
- 反馈应包含插件和 skill 版本、实际与预期行为、复现步骤或建议，以及重复报告的检索结果。新 issue 的标题应以插件名开头。访问或提交失败时，保留草稿并说明阻碍。提交结果不确定时，先确认是否已成功，再考虑重试。返回报告链接，或明确标注草稿尚未提交。
