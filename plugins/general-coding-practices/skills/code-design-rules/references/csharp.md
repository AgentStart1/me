# C# 与 .NET

- 优先使用 `Task`/`Task<T>`、`async`/`await`、异步 I/O 和项目已有的请求或服务生命周期。将 `CancellationToken` 传递给支持取消的调用。task 不会自动形成结构化的父子生命周期；后台任务需要明确管理和观察，包括关闭过程。
- `Task.WhenAll` 会观察完成情况，但某项失败时不会取消同级任务。流程需要时，显式协调关联取消。
- 转换异常时，保留与相关取消令牌对应的 `OperationCanceledException`。不要把请求关闭转换成普通失败。释放所管理的取消源，并按需在 `finally` 或通过 `using`/`await using` 释放资源。
- 异步或 UI 路径避免 `.Result`、`.Wait()`、`Thread.Sleep` 和阻塞锁。优先使用可等待 API、`Task.Delay`、`SemaphoreSlim.WaitAsync` 或 channel。小型同步临界区仍可使用 `lock`，但不要在其中 await。
- 对适合的 CPU 任务使用 `Task.Run`，不要用它代替异步 I/O。取消 await 不会强行停止任意阻塞代码。
- 合适时优先使用不可变 record 和不可变集合。`readonly`、`init` 和 record 不会深度冻结其引用的可变对象。

支持时使用封闭的变体模型，或采用构造与派生类型受控的抽象 record。只在 `Success<T>` 中放置 `Value`，只在失败类型中放置 `Cause`；可空引用注解不强制保证运行时不变量。不要假定所有支持的语言版本都会对 record 层次提供穷尽性编译检查；显式处理不支持的状态和事件。

使用 XML 文档注释说明取消令牌的管理责任、执行上下文要求、错误和释放约定。通过受控任务完成验证取消与失败的区别、清理、UI 上下文和乱序结果。

## 回调与事件适配

优先使用基于 task 的 API。通过 `TaskCompletionSource<T>` 适配单次事件或回调；合适时使用 `RunContinuationsAsynchronously`，通过 `TrySetResult`/`TrySetException`/`TrySetCanceled` 处理终止路径之间的竞态，并管理取消注册。处理事件注册前已取消的情况；完成时退订并释放注册，包括同步回调的情况。重复事件使用 `IAsyncEnumerable<T>` 或 `Channel<T>`，明确容量、溢出或背压策略及释放语义。`async void` 仅用于框架要求的事件处理函数，并在该处处理错误；内部流程应返回 task。

官方参考：[.NET 任务取消](https://learn.microsoft.com/en-us/dotnet/standard/parallel-programming/task-cancellation)。
