# RecyclerView 最佳实践插件

本可移植插件提供 Android RecyclerView 指引，用于创建、审查和重构列表 UI 代码。

列表实现及更新、回收、分页或行状态问题使用通用 RecyclerView skill。哨兵 skill 范围更窄：诊断前插可见性、锚定或插入动画问题，适合时才评估哨兵，或实现用户明确要求的哨兵。

功能状态和副作用遵循独立于框架的 Host 约定；Android ViewModel 可将 Host 适配到视图生命周期。前插哨兵会改变差异位置，但屏幕外的哨兵不保证可见性或锚定。验证实际布局和状态恢复行为；Paging 页眉使用 `ConcatAdapter` 或 `insertHeaderItem`。

## 使用项目的独立性

adapter 和哨兵实现归使用插件的项目所有，使用正常 AndroidX 依赖。两个 skill 均不让项目依赖本 AI 插件安装；所需 Android、Gradle 和编译器插件仍为普通依赖。

## 内容

- `plugin.json` 声明可移植插件和客户端扩展。
- `skills/android-recyclerview-best-practice/SKILL.md` 提供 RecyclerView 指引。
- `skills/recyclerview-sentinel-viewholder/SKILL.md` 提供通过起始哨兵 ViewHolder 改善前插锚定的方法。

## 插件打包

`plugin.json` 是可移植元数据的权威来源。客户端清单与完整 skill 资源会生成到 `me.claude` 和 `me.codex`，请从这两个仓库安装。源 skill 使用可移植的 frontmatter。Claude 路由按 skill 目录保存在 `extensions.com.anthropic.claude.skillFrontmatter` 中，仅注入生成的 Claude skill。Codex 的 skill 文件保持源文件原样复制。

## 改进反馈

插件问题向 [storytellerF/me issues](https://github.com/storytellerF/me/issues) 反馈。报告前，skill 要求检索已打开和已关闭的 issue，使用脱敏或合成示例，并遵循用户已有的发布授权。优先复用已有报告；无法访问时，保留尚未提交的草稿。
