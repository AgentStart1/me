# me

一套可移植的 [Agent Plugins](https://agent-plugins.org) 插件集合，提供 Android 工具、客户端 UI 与编码指引、支持 ngrok 隧道的测试报告分享，以及共享 Alpine Docker 后端的并发 QEMU 工作客户机。

## 包含的功能

- Android 模拟器准备与配置，以及独立于测试框架的 Android 设备测试锁。
- Android、RecyclerView、客户端 UI 和通用工程指引，包括异步控制流、状态和并发的跨平台代码设计规则，以及 Kotlin/Android、Swift、TypeScript/JavaScript、Python、Rust 和 C#/.NET 参考。
- 测试报告和代码差异站点生成，可选通过 ngrok 分享。
- 持久 QEMU Alpine/Docker 环境，支持 Linux KVM、Windows WHPX 和可移植 TCG 回退，适用于 Linux Docker 容器及 Windows 工作流。容器之外的普通 Linux 宿主机可直接使用 Docker，无需本插件。Ubuntu 工作客户机可选固定版本的 Windows/WHPX VirGL 运行时以加速 OpenGL。
- 与所属插件一同打包的可移植 Claude agent 提示词。

本仓库是权威源码。每个 `plugins/*/plugin.json` 遵循 Agent Plugins 1.0.0，客户端元数据保存在反向域名形式的 `extensions` 中，共享完整 skill 资源。源 skill 使用可移植 frontmatter，其他 Agent Plugins 客户端可直接加载。Claude 路由按 skill 目录保存在 `extensions.com.anthropic.claude.skillFrontmatter`，只在生成 `me.claude` 时注入。Codex skill 文件原样复制。可复用 agent 提示词留在各插件 `agents/` 目录。

变更合入 `main` 或手动触发后，GitHub Actions 在 `me.claude` 和 `me.codex` 创建发行同步 PR。请从这两个仓库安装。

原 `kotlin-coding-practices` 插件已并入 [`general-coding-practices`](plugins/general-coding-practices/README.md#代码设计指引)。安装或更新该插件，并将显式 `kotlin-project-rules` 引用改为 `code-design-rules`。

## 使用项目的独立性

skill 通过项目自身代码、常规工具接口和外部编排工作。使用 AI 插件不要求向项目添加其安装路径、私有配置或辅助命令。Gradle 插件、Appium 驱动或扩展等正常依赖继续受支持并记录；用户明确要求的 AI 插件集成保持在指定范围。

## 改进反馈

每个插件的 skill 都包含可落实改进事项的上游反馈流程。报告发往 [storytellerF/me](https://github.com/storytellerF/me/issues)，先检查已打开和已关闭的 issue，使用脱敏或合成示例。发布遵循用户已有授权；没有授权时，agent 准备草稿。仅安装插件不授权公开发布。

## 安装

### Codex

Codex 用户请参考专用 [`me.codex`](https://github.com/storytellerF/me.codex) 仓库的安装说明。

### Claude Code

Claude Code 用户请参考专用 [`me.claude`](https://github.com/storytellerF/me.claude) 仓库的安装与迁移说明。

## 开发

构建、验证、CI 和发行同步见 [DEVELOPMENT.md](DEVELOPMENT.md)。

## 从虚拟机访问宿主模拟器

先选择路由和目标。宿主 ADB 服务通常使用 5037；每个模拟器有自己的控制台、ADB 端口对，常见为 5554/5555。使用所选模拟器的实测端点，不假定所有设备都是 5555。gvproxy 客户机宿主别名 `192.168.127.254` 可访问宿主回环，添加 Windows 代理前先检查现有路由。其他隔离虚拟网络可能需要限定范围的代理或防火墙规则。以下示例明确假定所选 ADB 端点为 5555，虚拟机子网为 `192.168.80.0/24`，宿主接口为 `192.168.80.1`：

```powershell
netsh interface portproxy add v4tov4 listenaddress=192.168.80.1 listenport=5555 connectaddress=127.0.0.1 connectport=5555
netsh advfirewall firewall add rule name="Android Emulator ADB 5555" dir=in action=allow protocol=TCP localport=5555 remoteip=192.168.80.0/24
```

确认端口代理条目存在：

```shell
netsh interface portproxy show all
```

确认宿主机正在监听：

```shell
netstat -ano | findstr "192.168.80.1:5555"
```

未监听时，检查接口地址、端口归属、代理条目和 IP Helper 服务状态。重启该服务会中断其他端口代理，应使用已安排的维护窗口，不采用一概停止、重启的变通处理。

[QEMU 客户机插件](plugins/qemu-guests/README.md#vm-与容器状态面板)为 MCP Apps 宿主提供只读虚拟机、服务健康和容器状态面板。

Android 工具还提供[模拟器状态与按需屏幕预览](plugins/android-emulator-profile/README.md#android-emulators-状态面板)及[设备租约面板](plugins/android-device-lock/README.md#device-leases-状态面板)。
