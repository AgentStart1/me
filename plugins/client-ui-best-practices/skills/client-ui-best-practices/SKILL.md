---
name: client-ui-best-practices
description: Use for client UI work, reviews, refactors, or bug fixes involving Android Views, Compose, iOS/UIKit/SwiftUI, desktop UI, or other main-thread event-loop frameworks. Keep the UI/main thread limited to view-tree mutation and rendering work; move business logic, I/O, data transforms, and long-running computation to structured asynchronous work; expose UI-ready state and one-time events through observable state such as StateFlow and SharedFlow.
---

# Client UI Best Practices

Build clients around a unidirectional state flow: asynchronous work produces immutable UI state; the UI observes it and renders on its required UI thread.

## Main-thread boundary

- Reserve the UI/main thread for framework-required work: handling short UI callbacks, adding or removing views, and `measure`, `layout`, `draw`, recomposition, or equivalent rendering work.
- Keep UI callbacks short. Capture user intent and delegate it immediately; never run network, disk, database, parsing, crypto, image processing, or expensive collection transforms inline.
- Do not use the main thread as a generic business-logic dispatcher. A small, pure state update is acceptable only when it is demonstrably cheap.
- Return to the UI thread only to render observed state or perform an API that explicitly requires it.

## State-driven architecture

- Model durable screen data as an immutable `UiState` exposed as `StateFlow<UiState>` (or the platform's equivalent observable state).
- Model one-time effects—navigation, snackbar/toast, permission request, or external action—as a separate `SharedFlow<UiEffect>` or event stream. Do not encode a consumable event in persistent state.
- Let the ViewModel, presenter, or controller own asynchronous work and transform domain results into UI-ready state. Keep views declarative: observe, render, and send intents.
- Treat operators on observable data as real work. Run `map`, `filter`, `flatMap*`, `combine`, sorting, grouping, parsing, and other non-trivial transformations off the UI thread, even when the final state is observed by the UI.
- Use lifecycle-aware collection. Start and stop observation with the visible UI lifecycle; do not keep a view or screen alive through a long-lived collector.
- Publish complete immutable snapshots. Avoid exposing mutable collections or state that the UI can mutate.

## Observable transformation scheduling

Keep non-trivial work in an observable pipeline off the UI scheduler on every client platform. This includes `map`, filtering, flattening, combining streams, sorting, grouping, parsing, formatting, and mapping domain data to UI models. Use the platform's upstream/background scheduling operator or executor, and switch to the UI scheduler only at the rendering boundary.

Verify the scheduling semantics of the framework in use: some operators affect only upstream work, and hot streams may retain the scheduler on which they were created. Do not assume that observing a stream on the UI thread makes earlier transformations safe.

## Development-time enforcement

Do not expect a platform to recognize code semantically as business logic. Combine three controls:

1. Mark business entry points with static worker-thread annotations when available.
2. Add debug/test assertions that fail when non-trivial business work enters the UI thread or event-loop queue.
3. Enable platform diagnostics and trace UI stalls to catch blocking operations and unannotated paths.

Keep crash penalties and preconditions debug- or test-only unless release termination is an explicit product decision. Distinguish business work running on the UI thread from background work touching UI objects; many built-in wrong-thread checkers detect only the latter.

### Android

Enable `StrictMode.ThreadPolicy` from `Application.onCreate` in debug builds so the main thread receives the thread-local policy:

```kotlin
if (BuildConfig.DEBUG) {
    StrictMode.setThreadPolicy(
        StrictMode.ThreadPolicy.Builder()
            .detectDiskReads()
            .detectDiskWrites()
            .detectNetwork()
            .detectCustomSlowCalls()
            .penaltyLog()
            .build()
    )
}
```

Annotate non-UI entry points with `@WorkerThread` for Android Lint and add a runtime guard where a violation must be unmissable:

```kotlin
@WorkerThread
fun rebuildSearchIndex(items: List<Item>) {
    if (BuildConfig.DEBUG) {
        StrictMode.noteSlowCall("rebuildSearchIndex")
        check(Looper.myLooper() != Looper.getMainLooper()) {
            "rebuildSearchIndex must not run on the main thread"
        }
    }
    // CPU- or I/O-intensive work
}
```

Treat `noteSlowCall` as an explicit marker, not an elapsed-time detector. `StrictMode` catches configured disk, network, and marked calls; it does not identify arbitrary CPU work, coroutine bodies, or Flow transformations as business logic. Use Android Studio System Trace or Perfetto to locate main-thread stalls and janky frames. Use `penaltyDeath()` only in focused debug or test runs when immediate failure is useful.

### Apple platforms

Guard non-UI entry points in debug builds with `dispatchPrecondition(condition: .notOnQueue(.main))` and, when thread identity rather than queue identity matters, `precondition(!Thread.isMainThread)`. Do not assume `async` or `Task` implies background execution; actor or executor inheritance can keep work on the main actor.

Use Xcode's Main Thread Checker to catch UIKit/AppKit access from a background thread; do not treat it as a detector for business work running on the main thread. Use Instruments Hangs and Time Profiler to find busy or blocked main-thread intervals.

### Desktop and web event loops

- Swing: assert `!SwingUtilities.isEventDispatchThread()` at non-trivial business entry points.
- JavaFX: assert `!Platform.isFxApplicationThread()`.
- WPF: retain the UI `Dispatcher` and assert that `CheckAccess()` is false before background-only work. WinUI: make the equivalent assertion with `DispatcherQueue.HasThreadAccess`. Use the Application Timeline or profiler to inspect UI-thread stalls.
- Qt: assert `!QThread::isMainThread()` on Qt 6.8+, or compare the current thread with the application thread on older versions.
- Browser UI: observe `"longtask"` entries with `PerformanceObserver` and inspect the DevTools Performance trace; move CPU-intensive work to a Web Worker. Long Tasks report event-loop stalls, not semantic business-code violations.

## Kotlin/Android example

```kotlin
data class ProfileUiState(
    val isLoading: Boolean = false,
    val profile: Profile? = null,
    val error: String? = null,
)

class ProfileViewModel(
    private val repository: ProfileRepository,
) : ViewModel() {
    private val _uiState = MutableStateFlow(ProfileUiState())
    val uiState = _uiState.asStateFlow()

    private val _effects = MutableSharedFlow<ProfileEffect>()
    val effects = _effects.asSharedFlow()

    fun refresh() = viewModelScope.launch {
        _uiState.update { it.copy(isLoading = true, error = null) }
        runCatching { withContext(Dispatchers.IO) { repository.loadProfile() } }
            .onSuccess { profile ->
                _uiState.update { it.copy(isLoading = false, profile = profile) }
            }
            .onFailure { error ->
                _uiState.update { it.copy(isLoading = false, error = error.message) }
            }
    }
}
```

Collect `uiState` and `effects` using lifecycle-aware APIs, then perform view mutation or Compose rendering in the collector. Prefer injecting dispatchers when testability or dispatcher selection is meaningful; use `Dispatchers.IO` for blocking I/O and `Dispatchers.Default` for CPU-bound work.

For Kotlin Flow, place `flowOn` after the upstream transformations that need a background dispatcher and before `stateIn`, `shareIn`, or collection. `flowOn` changes only operators above it; it does not move downstream collectors or already-hot `StateFlow`/`SharedFlow` work.

```kotlin
val uiState: StateFlow<FeedUiState> = repository.observeFeed()
    .map { items -> items.sortedByDescending(Item::updatedAt).map(Item::toUiModel) }
    .map { models -> FeedUiState(items = models) }
    .flowOn(Dispatchers.Default)
    .stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = FeedUiState(),
    )
```

## Review checklist

- Identify every expensive or blocking operation reachable from a UI callback, render function, or main-thread collector; move it to a structured asynchronous boundary.
- Enable the platform's strict diagnostics in debug builds and place worker-thread assertions at important business boundaries.
- Verify separately that background code does not touch UI objects and that business code does not run on the UI thread; one checker rarely covers both directions.
- Inspect observable pipelines on every client platform as well as callbacks: ensure non-trivial transformations execute on an appropriate background scheduler or executor, upstream of the UI-observation boundary.
- For Kotlin Flow specifically, ensure non-trivial operators are upstream of an appropriate `flowOn`; use the platform-equivalent scheduling mechanism for other observable frameworks.
- Verify cancellation follows the screen, ViewModel, or feature lifecycle.
- Ensure a background result cannot update a destroyed or inactive UI directly; publish state and let lifecycle-aware observation render it.
- Separate persistent state from one-off effects, and define loading, empty, content, and failure states.
- Test state transitions, cancellation, error propagation, and that rendering receives UI-ready data without extra work.

## Delegated agent

For a cross-platform UI review or a refactor touching scheduling and state ownership, use
`../../agents/client-ui-architecture-reviewer.md`. Ask it to inspect the complete call path and return
actionable findings before delegating edits.
