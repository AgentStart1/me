---
name: client-ui-best-practices
description: 在移动端、Web 和桌面框架中实现、调试、审查或重构客户端 UI 状态、异步行为、生命周期、渲染及 UI 线程性能时使用。
---

# 客户端 UI 最佳实践

在 UI 线程完成渲染，将功能行为放入独立于 UI 框架的 `Host`。UI 观察不可变状态、渲染状态并调用 Host 操作。

## 使用项目的独立性

在项目自身代码和现有架构中实现 Host 与状态边界。不要在项目构建、运行时或文档中加入对本 AI 插件、助手专用包或参数的依赖，也不要要求调用其 agent。实现所需的 UI 框架、编译器或 Gradle 插件和测试库仍属于正常依赖。

## UI 边界

- UI 或事件循环线程只处理短回调，以及框架要求的渲染或视图修改。
- 网络、磁盘、数据库、解析、加密、图像处理、排序、分组等非轻量工作移出 UI 线程。
- 只在渲染状态或调用明确要求 UI 线程的 API 时切回 UI 线程。后台任务不得直接更新 UI 对象。
- 通过感知生命周期的订阅观察状态和副作用，避免视图与收集任务的生命周期失配。

## Host 约定

每个功能 Host 必须：

- 管理功能状态、一次性副作用、操作和异步协调。
- 不依赖 UI 控件、视图控制器、composable、组件等框架专用渲染类型。
- 暴露不可变状态、单独的副作用流，以及公开的用户或生命周期操作。
- 使用由应用管理、通过注入提供的串行协调执行器。即使名称包含 `main`，它也不是平台 UI 线程。
- 将 Host 状态修改和副作用发送限制在该串行执行器内。除非明确需要并发访问状态，否则不要添加锁或并行修改。
- 只把阻塞或 CPU 密集的部分切换到适当的工作执行器，修改状态前先恢复 Host 协调上下文。
- 注入会影响行为的调度器、时钟和异步依赖，让测试能够控制它们。
- 将取消保留为控制流。串行执行器或 actor 不会让跨越挂起点的完整操作串行化；通过取消、操作串行化或请求标识，显式阻止已被取代的任务发布过时状态。
- 提供确定的取消机制，由管理 Host 的页面、控制器、presenter 或其他组件负责。

与平台无关的结构：

```text
Host(dependencies, dispatchers):
    state  = observable immutable initialState
    effects = observable oneTimeEvents
    scope  = serialScope(dispatchers.coordination)

    action Refresh:
        scope.launch:
            state = state.with(loading = true)
            result = dispatchers.io.run { repository.load() }
            state = reduce(state, result)

    close:
        scope.cancel()
```

## 状态、副作用与工作

- 将需要持续渲染的数据发布为不可变状态快照。不要向 UI 直接暴露可变集合或领域对象。
- 导航、临时消息、权限请求和外部操作通过独立的一次性副作用通道发布。
- 非轻量的可观察数据转换，应在值到达 UI 订阅者之前完成，并调度到适当的工作执行器。
- 支持时，将数据库读取作为可观察数据源。阻塞写入通过 Host 命令边界或现有应用写入器执行。
- 保持事件处理函数轻量：将框架事件转换成 Host 操作，不从渲染代码启动业务任务。

## 平台参考

只阅读目标平台对应的参考：

- Android Views 或 Compose 与 Kotlin：[`references/android-kotlin.md`](references/android-kotlin.md)
- iOS 与 Swift：[`references/ios-swift.md`](references/ios-swift.md)
- React：[`references/react.md`](references/react.md)
- 其他桌面或事件循环框架：[`references/desktop.md`](references/desktop.md)

## 验证

- 不启动 UI 运行时，测试 Host 状态转换、副作用、错误、取消、顺序和调度器选择。
- UI 测试覆盖渲染、事件接线、生命周期集成和无障碍功能。
- 双向验证：昂贵工作不能占用 UI 线程，后台工作不能修改 UI 对象。
- 调查 UI 停顿时，使用平台诊断或性能分析证据。

## 上游改进反馈

- 发现有明确改进方向的插件缺陷或可复用的改进建议时，向 [storytellerF/me](https://github.com/storytellerF/me/issues) 反馈，并注明插件和 skill。若问题仅属于当前项目，且没有插件缺陷的证据，则不在此范围内。先完成主要任务，再处理不影响当前工作的反馈。
- 搜索或发布之前，将证据整理为不含隐私的最小摘要或合成复现案例。不得泄露原始对话、私有代码、日志、截图、凭据、个人或账户信息，以及私有路径和 URL。如果无法安全披露，就只在本地保留发现。
- 搜索已打开和已关闭的 issue，阅读可能匹配的报告及其解决方案。优先复用已有报告；如果是不同的回归问题或尚未覆盖的场景，可另建 issue 并关联原报告。发布新 issue 或有实质帮助的评论必须已经获得用户授权；本规则本身不授予发布权限。未获授权时，准备一份尚未提交的草稿。
- 反馈应包含插件和 skill 版本、实际与预期行为、复现步骤或建议，以及重复报告的检索结果。新 issue 的标题应以插件名开头。访问或提交失败时，保留草稿并说明阻碍。提交结果不确定时，先确认是否已成功，再考虑重试。返回报告链接，或明确标注草稿尚未提交。
