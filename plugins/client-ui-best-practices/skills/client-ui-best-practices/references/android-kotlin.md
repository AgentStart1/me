# Android and Kotlin Host

Use a `CoroutineScope` with an injected application-defined serial dispatcher for Host coordination. Do not confuse that dispatcher with `Dispatchers.Main`, which remains reserved for Android UI work.

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
    private var refreshGeneration = 0L // Mutated only by hostScope coordination.

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

- Collect render state with lifecycle-aware APIs such as `collectAsStateWithLifecycle()` or `repeatOnLifecycle`.
- Collect one-time effects in a lifecycle-aware coroutine launched by the UI owner.
- Put CPU-heavy Flow operators upstream of `flowOn(dispatcher.default)`.
- Propagate `CancellationException`; cancellation must not publish a failure state.
- A serial dispatcher serializes execution between suspensions, not an entire
  asynchronous request. For overlapping refreshes, cancel prior work, serialize
  complete operations, or reject completions with a request identity before reduction.
- Use `StrictMode`, explicit Looper assertions, and profilers when diagnosing main-thread work.
