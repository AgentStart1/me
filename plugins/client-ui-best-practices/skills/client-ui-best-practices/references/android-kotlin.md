# Android 与 Kotlin Host

使用注入了应用自定义串行调度器的 `CoroutineScope` 协调 Host。不要将此调度器与 `Dispatchers.Main` 混淆，后者仍专用于 Android UI 工作。

```kotlin
class ProfileHost(
    private val repository: ProfileRepository,
    private val dispatcher: AppDispatcher,
) {
    private val hostScope = CoroutineScope(SupervisorJob() + dispatcher.coordination)
    private val _state = MutableStateFlow(ProfileState())
    val state = _state.asStateFlow()
    private val _effects = MutableSharedFlow<ProfileEffect>()
    val effects = _effects.asSharedFlow()
    private var refreshGeneration = 0L // 仅由 hostScope 的协调流程修改。

    fun refresh() = hostScope.launch {
        val generation = ++refreshGeneration
        _state.update { it.copy(isLoading = true) }
        val result = try {
            Result.success(withContext(dispatcher.io) { repository.loadProfile() })
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (failure: Exception) {
            Result.failure(failure)
        }
        ensureActive()
        if (generation == refreshGeneration) {
            _state.update { current -> current.reduce(result) }
        }
    }

    fun close() = hostScope.cancel()
}
```

- 通过 `collectAsStateWithLifecycle()` 或 `repeatOnLifecycle` 等感知生命周期的 API 收集渲染状态。
- 在 UI 管理者启动、感知生命周期的协程中收集一次性副作用。
- CPU 密集的 Flow 操作符放在 `flowOn(dispatcher.default)` 上游。
- 传播 `CancellationException`，取消不能发布失败状态。
- 串行调度器只让挂起点之间的执行串行化，不会让整个异步请求串行化。刷新重叠时，取消先前任务、串行执行完整操作，或在归约前通过请求标识拒绝过时的完成结果。
- 诊断主线程工作时，使用 `StrictMode`、显式 Looper 断言和性能分析器。
