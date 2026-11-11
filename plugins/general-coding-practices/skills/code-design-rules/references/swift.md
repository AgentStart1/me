# Swift 与 Apple 平台

- 对有明确管理者的并发任务，优先使用 `async`/`await`、`async let` 和任务组。非结构化 `Task` 需要明确的管理责任和取消机制；不要把 `Task.detached` 当作会继承生命周期或 actor 隔离的子任务。
- 共享状态使用 actor 或已有的隔离管理者。`@MainActor` 用于与 UI 绑定的状态，不应覆盖全部计算。操作挂起期间，actor 可以处理其他任务；提交结果前重新检查请求标识。
- 取消是协作式的。传播 `CancellationError`，适时使用 `Task.checkCancellation()`，并处理通过其他错误类型表示取消的 API。不要把管理者的取消转换为普通错误状态。
- 协作式执行器上避免 `Thread.sleep`、信号量等待和阻塞队列桥接。使用异步 API 和 `Task.sleep`；不可避免的阻塞互操作应隔离到合适的有界执行器，不要假定 `Task` 会自动将其转移到别处执行。
- 优先使用 `let`、值类型和带关联值的枚举。`let` 不会冻结可变类的实例。按隔离约定使用 `Sendable`；没有可验证的边界时，不要通过未经检查的协议遵循来压制违规提示。

```swift
enum LoadState<Value> {
    case idle
    case loading
    case success(Value)
    case failure(any Error)
}
```

使用穷尽的 `switch`。仅当缺失值合法时，成功状态才使用 `Value?`。在文档注释中说明管理责任、隔离、取消和错误（使用 `///`，按需补充 Parameters/Returns/Throws）。通过受控异步测试验证取消、actor 重入、被新请求取代的完成结果和任务清理。

## 回调与委托适配

优先使用原生异步 API。将单次完成处理函数封装为 checked continuation，成功或失败时恰好恢复一次。checked continuation 不会自动传播任务取消；应由能安全处理竞态的管理者协调注册、取消和完成，包括注册前已取消的情况。重复的委托或监听器事件使用 `AsyncStream` 或 `AsyncThrowingStream`，明确缓冲策略并在终止时清理。保留必需的委托作为适配层，不要将流程逻辑分散其中。

官方参考：[Swift 并发](https://docs.swift.org/swift-book/documentation/the-swift-programming-language/concurrency/)。
