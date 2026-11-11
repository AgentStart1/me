# Android 设备锁

通过随包 `scripts/adb-device-lock.sh` 辅助工具，让任何测试框架在 Android 真机或模拟器上的设备测试串行访问设备。设备端目录和经过令牌校验的租约是权威状态；获取、续租和释放流程见 `skills/android-device-lock/SKILL.md`。

适用于共享设备测试会话及其准备工作，也可检查设备占用和租约归属。仅在宿主机运行的 JVM 测试不需要设备租约；只读模拟器清单和屏幕预览由模拟器工具提供。

## 独立于项目使用

agent 通过绝对路径调用已安装插件的锁工具，从项目目录执行原有测试命令，再释放租约。无需向项目添加插件脚本、锁依赖、测试包装器、CI 修改或配置。正常 Android、Gradle 和测试框架依赖不受影响。项目集成属于需要明确提出的独立任务。

共享设备的所有项目使用同一设备端锁路径。元数据中的项目目录和测试名只标识归属。令牌文件和临时编排留在项目外。定位已安装工具和多步骤操作见 skill。

租约修改使用设备端原子 `<lock-path>.guard`，覆盖过期接管、令牌校验、续租和释放。每个参与者必须使用相同版本和路径的工具。中断的 guard 和不可读元数据需要检查；仅凭目录存在时间无法证明设备工作已停止。自定义锁路径位于 `/data/local/tmp` 下。固定时长 `run` 租约必须长于整个命令；更长操作需要手动续租，并在丢失归属时取消。

宿主机租约控制器使用 Python 3.10+ 执行设备操作、带类型的归属检查及转义。它尝试可用的 `python3` 和 `python`；必要时通过 `ANDROID_DEVICE_LOCK_PYTHON` 指定解释器。JSON 或字段类型无效时，归属保持未知，不通过文本模式提取到期时间或令牌。

## 原生 Python 入口

Windows 或 Unix 可使用相同命令和选项运行 `python /absolute/plugin/scripts/adb-device-lock.py`。`.sh` 入口只选择 Python 3.10+ 解释器并转发参数。控制器保留设备 guard 和令牌协议，负责命令取消、子进程清理和租约释放。

## Device Leases 状态面板

在支持 MCP Apps 的宿主应用全局侧栏或对话标签页打开 **Device Leases**，或调用 `android_device_lock_status`。只读面板显示各 ADB 设备的连接、租约状态、任务、项目目录名、归属宿主机和 PID，以及剩余租约时长。可按设备、序列号、任务或归属过滤，手动刷新，或在可见时启用每十秒自动刷新。

各状态有明确区别：

- **Free**：观察时设备可访问，且不存在锁目录。
- **Held**：可读元数据包含尚未到期的租约。
- **Expired**：租约已到期，但锁目录仍存在。面板不会删除它。
- **Unknown/unavailable**：元数据损坏、路径不可访问或无法查询设备。应视为归属未知，不能视为空闲。

倒计时根据服务端报告的剩余时长及面板经过时间计算。归零时请求刷新以核实归属，绝不自动释放设备。现有工具不持久保存等待队列，面板也不编造队列。到期判断采用观察宿主机的时钟，与工具时间戳基准一致。

收集器只输出允许展示的字段，省略 `owner_token`、原始元数据和完整项目路径。观察面板不会获取、续租、释放或清理租约，也不会启动设备测试会话。

## 本地 MCP 运行时

安装 [uv](https://docs.astral.sh/uv/)，并让 ADB 在本地 stdio MCP 服务所在环境可用。兼容清单注册 `.mcp.json`：

```bash
uv run --script scripts/status-server.py
# JSON 备用方式：
python3 scripts/lock_status.py
```

ADB 查找依次考虑 `ANDROID_ADB_COMMAND`、PATH、`ANDROID_HOME`、`ANDROID_SDK_ROOT` 和 `~/android-sdk`。ADB 常用服务环境变量仍然可用；查询可能启动本地 ADB 服务。所有设备读取都显式指定序列号。

Git Bash 调用 Windows ADB 时，租约工具保留 Android 路径，只将待上传的本地元数据文件转换为 Windows 原生路径。

插件和 skill 现使用 `android-device-lock` 标识。发布后，用此包替换旧安装。切换到新默认锁路径之前，先结束已有测试，让所有运行器和状态收集器使用相同路径。默认观察路径为 `/data/local/tmp/android-device-test.lock.d`。流程使用自定义 `--lock-path` 时，将 `ANDROID_DEVICE_LOCK_PATH` 设为同一绝对 Android 路径。Shell 引用会保留空格和特殊字符，不将路径作为代码执行。

面板要求宿主应用支持 MCP Apps，以及 OpenAI 全局侧栏和对话入口。本改动不部署远程 ChatGPT 服务。共享 UI 构建与测试说明见仓库中的 `scripts/android-status/README.md`。

## 插件打包

`plugin.json` 是可移植元数据的权威来源。客户端清单与完整 skill 资源会生成到 `me.claude` 和 `me.codex`，请从这两个仓库安装。源 skill 使用可移植的 frontmatter。Claude 路由按 skill 目录保存在 `extensions.com.anthropic.claude.skillFrontmatter` 中，仅注入生成的 Claude skill。Codex 的 skill 文件保持源文件原样复制。

## 取消、清理与恢复

租约元数据由 `scripts/lock-metadata.py` 使用 JSON 编码的占位值，从随包 `scripts/lock.json.template` 渲染。这两项资源必须与已安装辅助工具一同保留，字段提取和渲染保持严格 JSON 验证。

远程租约删除失败时，`release` 返回非零并保留归属令牌供恢复。命令成功但清理失败时，`run` 也返回非零；已有命令失败或信号退出状态保持不变。核对设备连接和归属后，使用保留令牌重试释放。

Windows 使用 Ctrl+C 或原生 Ctrl+Break 平滑取消。Git Bash `kill -TERM` 强制终止原生 Python，无法执行清理；恢复前检查保留令牌和设备 guard。原生等待在命令运行期间分派信号，再停止自有命令树，最后释放。

`run` 在释放租约前停止剩余后代，即使命令根进程已退出。Windows 使用 Job Object；Unix 命令必须将设备 worker 留在自有进程组，不得 daemonize 或创建脱离会话。无法确认进程树清理时，保留租约和归属令牌供恢复。Windows shebang 入口通过 Git Bash 使用声明的解释器和原参数，该解释器必须在 Git Bash 环境可用。

## 改进反馈

插件问题向 [storytellerF/me issues](https://github.com/storytellerF/me/issues) 反馈。报告前，skill 要求检索已打开和已关闭的 issue，使用脱敏或合成示例，并遵循用户已有的发布授权。优先复用已有报告；无法访问时，保留尚未提交的草稿。

## 开发

离线回归套件及源码检出前提见[仓库开发文档](../../DEVELOPMENT.md#shell-边界回归测试)。
