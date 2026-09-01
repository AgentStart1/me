---
name: client-ui-best-practices
description: Use for client UI work involving state ownership, threading, lifecycle, or rendering in Android Views/Compose, iOS, desktop, and similar event-loop frameworks.
---

# Client UI Best Practices

Keep rendering on the UI thread. Put feature behavior in a UI-framework-independent `Host`: the UI observes immutable state, renders it, and invokes Host actions.

## UI boundary

- The UI/main thread is for short callbacks and framework-required view mutation or rendering only.
- Never run network, disk or database I/O, parsing, crypto, image processing, sorting, grouping, or other non-trivial business work from a UI callback, render function, or main-thread collector.
- Return to the UI thread only to render state or use an API that explicitly requires it. Background work must not update UI objects directly.
- Use lifecycle-aware observation so views do not outlive their collectors.

## Host execution model

A feature `Host` owns its state, effects, and asynchronous behavior. It must not depend on Compose, Android Views, or another UI framework type.

- Give every Host a private `hostScope` using an injected custom serial dispatcher, such as `dispatcher.main`. Despite the name, it is **not** the UI dispatcher or `Dispatchers.Main`; it is the Host's application-defined coordination dispatcher.
- Launch all Host-owned coroutines in `hostScope`. State changes, effect emission, and coordination stay in this scope, which serially confines Host state; do not add locks or parallel Host mutations unless the feature explicitly needs concurrent state access.
- Switch only the expensive portion of work: use `dispatcher.io` for blocking I/O and `dispatcher.default` for CPU-bound work or non-trivial Flow transformations. Resume in `hostScope` before changing Host state or emitting effects.
- Expose read-only state/effects and public actions only. The screen, ViewModel, presenter, or controller that owns the Host owns cancellation.
- Inject dispatchers and other asynchronous dependencies that affect behavior so coroutine tests can control them.

```kotlin
class ProfileHost(
    private val repository: ProfileRepository,
    private val dispatcher: AppDispatcher,
) {
    private val hostScope = CoroutineScope(SupervisorJob() + dispatcher.main)

    private val _uiState = MutableStateFlow(ProfileUiState())
    val uiState = _uiState.asStateFlow()

    private val _effects = MutableSharedFlow<ProfileEffect>()
    val effects = _effects.asSharedFlow()

    fun refresh() = hostScope.launch {
        _uiState.update { it.copy(isLoading = true, error = null) }
        runCatching {
            withContext(dispatcher.io) { repository.loadProfile() }
        }.onSuccess { profile ->
            _uiState.update { it.copy(isLoading = false, profile = profile) }
        }.onFailure { error ->
            _uiState.update { it.copy(isLoading = false, error = error.message) }
        }
    }

    fun close() = hostScope.cancel()
}
```

`AppDispatcher` is application-defined: `main` serializes Host work, while `io` and `default` select I/O and CPU execution. The UI framework's main dispatcher remains reserved for rendering.

## State, effects, and observable work

- Publish durable screen data as immutable `UiState` through `StateFlow` (or the platform equivalent). Do not expose mutable collections or domain objects to the UI.
- Publish one-time work—navigation, snackbar/toast, permissions, or external actions—through a separate effect stream such as `SharedFlow<UiEffect>`.
- In Compose, collect rendering inputs into Compose `State`, normally with `collectAsStateWithLifecycle()`. Use a lifecycle-aware `LaunchedEffect` collector for one-time effects; never launch business work directly from a composable.
- Treat Flow operators as work. Put non-trivial `map`, `filter`, `combine`, flattening, sorting, grouping, parsing, and UI-model mapping upstream of `flowOn(dispatcher.default)`. `flowOn` moves only upstream operators, not collectors or already-hot flows.
- Treat database reads as observable sources (for example, DAO `Flow`s). Execute blocking writes on `dispatcher.io` through the feature's command boundary or an existing application-wide writer; UI code must not call a DAO directly.

```kotlin
val uiState: StateFlow<FeedUiState> = repository.observeFeed()
    .map { items -> items.sortedByDescending(Item::updatedAt).map(Item::toUiModel) }
    .map { models -> FeedUiState(items = models) }
    .flowOn(dispatcher.default)
    .stateIn(hostScope, SharingStarted.WhileSubscribed(5_000), FeedUiState())
```

## Verification and tests

- Test Host state transitions, effects, errors, cancellation, and ordering with coroutine tests and test dispatchers. Compose/UI tests cover rendering, event wiring, and accessibility.
- In debug or test builds, enable platform diagnostics and add worker-thread assertions at meaningful expensive-work boundaries. On Android, use `StrictMode` for disk/network violations and `Looper` checks for explicit CPU-work guards; use platform profilers to find UI stalls.
- Verify both directions: business work stays off the UI thread, and background work does not update UI objects directly.

## Review checklist

- Are feature actions and Host state mutations confined to `hostScope` and its custom serial dispatcher?
- Do blocking I/O and CPU-heavy work explicitly switch to `dispatcher.io` and `dispatcher.default`?
- Are state and effects immutable, separate, lifecycle-aware, and UI-ready?
- Do Flow transformations run upstream of the appropriate `flowOn` rather than in UI collection?
- Does cancellation follow the Host owner, and can the Host be tested without a UI runtime?
