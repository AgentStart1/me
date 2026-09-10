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

    fun refresh() = hostScope.launch {
        _state.update { it.copy(isLoading = true) }
        val result = runCatching {
            withContext(dispatcher.io) { repository.loadProfile() }
        }
        _state.update { current -> current.reduce(result) }
    }

    fun close() = hostScope.cancel()
}
```

- Collect render state with lifecycle-aware APIs such as `collectAsStateWithLifecycle()` or `repeatOnLifecycle`.
- Collect one-time effects in a lifecycle-aware coroutine launched by the UI owner.
- Put CPU-heavy Flow operators upstream of `flowOn(dispatcher.default)`.
- Use `StrictMode`, explicit Looper assertions, and profilers when diagnosing main-thread work.
