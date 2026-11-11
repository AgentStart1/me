# 通用编码实践插件

本插件提供项目协作规则，以及面向 README 和项目指引的文档维护规则。插件根目录还包含可移植、兼容 Claude 的文档 agent 提示词。

协作 skill 适用于各类项目开发任务；代码设计指引聚焦控制流、异步任务管理和状态模型。文档指引适用于文档维护请求，以及影响已记录行为或流程的变更。仅修改内部实现且现有说明仍然准确时，不必修改文档。

## 使用项目的独立性

这些指引让使用插件的项目独立于 AI 插件实现细节：标准项目命令和正常依赖在未安装本助手插件时仍可使用。Gradle 插件、Appium 驱动或扩展及所需库仍属于普通项目依赖；协作和文档 skill 将其与助手安装路径及编排信息区分开。

## 包含的指引

- 按已有计划自主推进项目协作，只有阻碍导致无法继续时才向用户询问，并落实隐私、依赖、生成文件和聚焦提交的实践。
- 先找根因再调试，优先修正资源归属、生命周期和边界结构，避免不断叠加补丁；同时保留必要的恢复机制和不泄露隐私的诊断信息。
- 注释解释意图和约束，记录有用的 API 约定，让变通处理和 TODO 有明确的后续行动。
- 聚焦的测试、格式化、lint、静态分析和构建验证。
- 覆盖单元、集成、UI 和 E2E 的测试设计与审查：测试名称与断言结果一致，将独立约定拆开，同时保留断言、输入矩阵和确有依赖的流程。普通改动聚焦新增及受影响的测试。
- 按读者维护文档：用户指引放在 `README.md`，开发指引放在 `DEVELOPMENT.md`，AI 指引放在 `AGENTS.md`。
- 文档语言遵循用户明确要求；没有明确要求时，已有文档沿用主要语言，新文档默认使用当前对话语言。保留多语言分工，采用自然、准确的技术表达。
- 跨平台代码设计：顺序式异步控制流和回调或监听器适配，以及异步任务管理、取消、不可变变体、显式转换和过时结果拒绝。
- 可移植的 Claude 文档 agent 委派。

skill 委派给随包提供的 Claude agent 时，父 agent 必须等待所需最终报告，再执行依赖工作或给出最终回复。

## 代码设计指引

`code-design-rules` skill 涵盖可读控制流、回调和监听器适配、状态建模及并发。它提供共享原则，只加载相关的平台参考：Kotlin/Android、Swift、TypeScript/JavaScript、Python/asyncio、Rust 和 C#/.NET。各参考将原则对应到原生 API、状态类型、文档规范和验证实践。

此插件取代 `kotlin-coding-practices` 及其 `kotlin-project-rules` skill。更新插件市场后，安装或更新 `general-coding-practices`，并通过客户端插件管理器移除已停用的 Kotlin 插件。显式 skill 引用改为 `code-design-rules`。Kotlin 协程、密封状态和 KDoc 指引保留在 Kotlin 参考中。安装同步后的更新后，开启新的 Codex 对话。

## 插件打包

`plugin.json` 是可移植元数据的权威来源。客户端清单与完整 skill 资源会生成到 `me.claude` 和 `me.codex`，请从这两个仓库安装。源 skill 使用可移植的 frontmatter。Claude 路由按 skill 目录保存在 `extensions.com.anthropic.claude.skillFrontmatter` 中，仅注入生成的 Claude skill。Codex 的 skill 文件保持源文件原样复制。

## 改进反馈

插件问题向 [storytellerF/me issues](https://github.com/storytellerF/me/issues) 反馈。报告前，skill 要求检索已打开和已关闭的 issue，使用脱敏或合成示例，并遵循用户已有的发布授权。优先复用已有报告；无法访问时，保留尚未提交的草稿。
