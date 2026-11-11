# 客户端 UI 最佳实践插件

本可移植插件提供客户端 UI 线程和状态驱动渲染指引。它定义独立于平台的 `Host` 边界，由 Host 管理可观察、可直接用于 UI 的状态和异步业务任务，让功能行为无需 UI 运行时也能测试。

实现或调查 UI 状态、异步更新、生命周期、渲染或响应性时，使用此 skill。Host 约定由 skill 内部应用，用户不必点名要求这种架构。

取消仍属于控制流，串行调度器和 actor 可以在挂起点交错处理异步请求。示例保留取消语义，并通过请求代次拒绝被取代的完成结果。Claude agent 路由适用于生成的 Claude 包；Codex 加载可移植 skill 指引。

## 使用项目的独立性

应用本指引得到的是项目自身的 UI 架构，不依赖 AI 插件或其 agent。所需 UI 库、编译器插件和构建插件仍是正常项目依赖。

## 内容

- `plugin.json` 声明可移植插件及客户端扩展。
- `skills/client-ui-best-practices/SKILL.md` 定义主线程边界、限制在注入的自定义串行调度器中的 `hostScope`、显式 Default/IO 切换、状态与副作用收集，以及无需 UI 的 Host 测试。
- `agents/client-ui-architecture-reviewer.md` 审查状态归属、Host 边界、调度、生命周期和可测试性；父 agent 在编辑或回复之前等待其最终报告。

## 本地插件市场条目

仓库插件市场将此插件注册为 `client-ui-best-practices`，路径为 `./plugins/client-ui-best-practices`。

## 插件打包

`plugin.json` 是可移植元数据的权威来源。客户端清单与完整 skill 资源会生成到 `me.claude` 和 `me.codex`，请从这两个仓库安装。源 skill 使用可移植的 frontmatter。Claude 路由按 skill 目录保存在 `extensions.com.anthropic.claude.skillFrontmatter` 中，仅注入生成的 Claude skill。Codex 的 skill 文件保持源文件原样复制。

## 改进反馈

插件问题向 [storytellerF/me issues](https://github.com/storytellerF/me/issues) 反馈。报告前，skill 要求检索已打开和已关闭的 issue，使用脱敏或合成示例，并遵循用户已有的发布授权。优先复用已有报告；无法访问时，保留尚未提交的草稿。
