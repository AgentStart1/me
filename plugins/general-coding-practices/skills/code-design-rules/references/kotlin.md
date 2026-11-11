# Kotlin 与 Android

## 原生术语与技术选择

- 优先使用 `suspend` API、`coroutineScope`、`supervisorScope`、`withContext`、`Flow`、`Channel`、`Mutex`、`Semaphore`、`StateFlow`、`SharedFlow` 和已有的应用或生命周期作用域。根据失败隔离需求，有意识地选择监督机制。
- 优先使用 `val` 和 `val x = if (a) b else c` 这样的表达式。只读集合接口和 `val` 不保证深度不可变。
- 新设计避免围绕原始 `Thread`、`thread`、`Runnable`、`HandlerThread`、`Executor`、`ExecutorService`、`Future` 或直接管理 Java 线程池展开。隔离必要的 Java 互操作，明确取消和关闭行为。
- 协程路径中避免 `synchronized`、监视器锁、`wait`/`notify`/`notifyAll` 和 `ReentrantLock`。优先采用明确的状态归属、actor、不可变快照、`Mutex.withLock` 或 channel。状态更新锁内避免执行可挂起的 I/O。
- 使用 `delay`，而非 `Thread.sleep`。无法避免的阻塞 I/O 放到适当的调度器；计算任务使用适合 CPU 工作的调度器。
- 将 `runBlocking` 限制在小型同步边界，例如 CLI 入口、旧系统集成或无法使用协程测试 API 的测试。说明为什么难以使用挂起接口；协程测试优先使用 `runTest`。
- 映射失败时重新抛出 `CancellationException`，`runCatching` 也会捕获它。仅切换调度器并不能让任意阻塞调用支持取消。
- 生命周期作用域限定任务存活时间，但不能阻止旧请求在新请求之后发布结果。在状态管理者提交结果时检查请求标识或代次。

## 状态与文档

使用携带不可变变体的密封接口或类，以及穷尽的 `when`：

```kotlin
sealed interface LoadState<out T> {
    data object Idle : LoadState<Nothing>
    data object Loading : LoadState<Nothing>
    data class Success<T>(val value: T) : LoadState<T>
    data class Failure(val cause: Throwable) : LoadState<Nothing>
}
```

结果必须非空时使用 `Success<Result>`；仅当不存在结果也是合法成功时，才使用 `Success<Result?>`。通过已有状态管理者（例如 `StateFlow`）发布快照，不修改已发布快照背后的对象。

只有能补充签名未表达的约定时，才使用 KDoc 链接以及 `@param`、`@return` 或 `@throws`。按需说明作用域和调度器的管理责任，以及 Flow 的收集语义。使用协程测试调度器和适当的单元或集成测试验证；Android 生命周期变更也可能需要 Android 测试。

## 回调与监听器适配

优先使用已有挂起 API。单次回调 API 使用 `suspendCancellableCoroutine`，配合取消清理和能安全处理竞态、最多恢复一次的协议；单独检查 `isActive` 与恢复操作并不构成原子操作。取消时注销回调，释放取消后才交付的资源。重复监听事件使用 `callbackFlow` 和 `awaitClose`，按事件约定选择缓冲方式并处理 `trySend` 失败。适配层放在 API 边界，让调用流程保持顺序式挂起代码的形式。

官方参考：[Kotlin 取消与超时](https://kotlinlang.org/docs/cancellation-and-timeouts.html)。
