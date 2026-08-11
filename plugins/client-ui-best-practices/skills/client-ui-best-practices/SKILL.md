---
name: client-ui-best-practices
description: Use for client UI work, reviews, refactors, or bug fixes involving Android Views, Compose, iOS/UIKit/SwiftUI, desktop UI, or other main-thread event-loop frameworks. Keep the UI/main thread limited to view-tree mutation and rendering work; move business logic, I/O, data transforms, and long-running computation to structured asynchronous work; expose UI-ready state and one-time events through observable state such as StateFlow and SharedFlow.
context: fork
agent: client-ui-architecture-reviewer
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
- In Compose, collect every value that affects rendering into Compose `State`, normally with `collectAsStateWithLifecycle()`. Read that state during composition; do not read mutable domain objects or launch asynchronous work directly from a composable.
- Encapsulate each screen or feature's observable state and asynchronous business tasks in a `Host`. A `Host` owns immutable state, exposes methods for the view to call, performs asynchronous work, and publishes UI-ready snapshots. It must not depend on Compose, Android views, or a UI lifecycle.
- Let a ViewModel, presenter, or controller own or adapt the `Host` to the screen lifecycle when necessary. Keep views declarative: observe, render, and call host methods directly—not through intent dispatching.
- Treat operators on observable data as real work. Place `map`, `filter`, `flatMap*`, `combine`, sorting, grouping, parsing, and other non-trivial transformations upstream of `flowOn(Dispatchers.Default)` or equivalent, so they execute off the UI thread even when the downstream is collected on the UI thread.
- Use lifecycle-aware collection. Start and stop observation with the visible UI lifecycle; do not keep a view or screen alive through a long-lived collector.
- Publish complete immutable snapshots. Avoid exposing mutable collections or state that the UI can mutate.

### Host boundary and tests

A `Host` is a platform-independent state holder and asynchronous task boundary, not a second name for a composable or a view. Expose read-only observable state and effects; keep mutation and coroutine launching private to the host. Inject dispatchers, scopes, repositories, clocks, or other external dependencies that affect asynchronous behavior.

This boundary makes business behavior testable without a UI runtime: instantiate the host in a coroutine test, call its public methods, and assert the resulting state/effects. Test loading, success, failure, cancellation, and state-transition ordering there. Compose tests should only cover rendering, user-event wiring, and accessibility semantics.

### Database observability

Treat the database as a reactive data source: reads are observable Flows that emit on every relevant table change; writes are commands dispatched through a global event stream.

- Expose database reads as `Flow` from DAO methods (e.g. Room `@Query` returning `Flow<List<T>>`). The Flow re-emits automatically when the underlying table changes, so the UI always reflects the latest persisted state without manual refresh.
- Route database writes through a global `SharedFlow<DbEvent>`. A dedicated writer collects events and executes suspend DAO methods on `Dispatchers.IO`, keeping write logic centralized and testable.
- Never observe or write to the database directly from a composable, UI callback, or Host constructor. The Host subscribes to the composed database Flow; a separate writer service subscribes to the event stream.
- Combine the database Flow with other upstreams (network, cache, preferences) inside the Host using `combine` or `flatMapLatest`, upstream of `flowOn(Dispatchers.Default)`.
- Keep database event types as a sealed interface so the writer can pattern-match all cases exhaustively. Include entity identity and payload in each event.

```kotlin
// --- Database events ---

sealed interface DbEvent {
    data class UpsertItem(val entity: ItemEntity) : DbEvent
    data class DeleteItem(val id: Long) : DbEvent
}

// --- DAO (Room) ---

@Dao
interface ItemDao {
    @Query("SELECT * FROM items ORDER BY updatedAt DESC")
    fun observeItems(): Flow<List<ItemEntity>>

    @Upsert
    suspend fun upsert(item: ItemEntity)

    @Query("DELETE FROM items WHERE id = :id")
    suspend fun deleteById(id: Long)
}

// --- Database writer ---

class DatabaseWriter(
    private val itemDao: ItemDao,
    private val eventFlow: SharedFlow<DbEvent>,
    private val scope: CoroutineScope,
    private val ioDispatcher: CoroutineDispatcher,
) {
    fun start() = scope.launch {
        eventFlow.collect { event ->
            withContext(ioDispatcher) {
                when (event) {
                    is DbEvent.UpsertItem -> itemDao.upsert(event.entity)
                    is DbEvent.DeleteItem -> itemDao.deleteById(event.id)
                }
            }
        }
    }
}

// --- Host (reads from DB, writes via events) ---

class ItemHost(
    private val itemDao: ItemDao,
    private val dbEvents: MutableSharedFlow<DbEvent>,
    private val repository: ItemRepository,
    private val scope: CoroutineScope,
    private val ioDispatcher: CoroutineDispatcher,
) {
    private val _uiState = MutableStateFlow(ItemUiState())
    val uiState = _uiState.asStateFlow()

    fun observe() = scope.launch {
        combine(
            itemDao.observeItems(),
            repository.observeNetworkStatus(),
        ) { items, status ->
            ItemUiState(
                items = items.map { it.toUiModel() },
                isOffline = status == NetworkStatus.Offline,
            )
        }
            .flowOn(Dispatchers.Default)
            .collect { _uiState.value = it }
    }

    fun deleteItem(id: Long) = scope.launch {
        dbEvents.emit(DbEvent.DeleteItem(id))
    }
}
```

- The database Flow drives the UI reactively: any insert, update, or delete on the observed tables triggers a new emission through the Host and into the UI state.
- Writes go through `dbEvents.emit(...)`, never through direct DAO calls from the Host. This keeps the write path observable, testable, and decoupled from the read path.
- For testing, replace the DAO with an in-memory fake that exposes a controllable `MutableSharedFlow`, and verify that emitted `DbEvent` values match expected writes.

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

## Kotlin/Compose example

```kotlin
data class ProfileUiState(
    val isLoading: Boolean = false,
    val profile: Profile? = null,
    val error: String? = null,
)

class ProfileHost(
    private val repository: ProfileRepository,
    private val scope: CoroutineScope,
    private val ioDispatcher: CoroutineDispatcher,
) {
    private val _uiState = MutableStateFlow(ProfileUiState())
    val uiState = _uiState.asStateFlow()

    private val _effects = MutableSharedFlow<ProfileEffect>()
    val effects = _effects.asSharedFlow()

    fun refresh() = scope.launch {
        _uiState.update { it.copy(isLoading = true, error = null) }
        runCatching { withContext(ioDispatcher) { repository.loadProfile() } }
            .onSuccess { profile ->
                _uiState.update { it.copy(isLoading = false, profile = profile) }
            }
            .onFailure { error ->
                _uiState.update { it.copy(isLoading = false, error = error.message) }
            }
    }
}

@Composable
fun ProfileRoute(host: ProfileHost) {
    val state by host.uiState.collectAsStateWithLifecycle()
    ProfileScreen(
        state = state,
        onRefresh = host::refresh,
    )
}
```

Collect `uiState` and `effects` using lifecycle-aware APIs, then perform view mutation or Compose rendering in the collector. In Compose, `collectAsStateWithLifecycle()` creates the rendering `State`; a `LaunchedEffect` collector is appropriate for one-time effects. Prefer injecting dispatchers when testability or dispatcher selection is meaningful; use `Dispatchers.IO` for blocking I/O and `Dispatchers.Default` for CPU-bound work.

The host can be exercised in a coroutine test without Compose or Android instrumentation:

```kotlin
@Test
fun refresh_publishesLoadedProfile() = runTest {
    val host = ProfileHost(
        repository = FakeProfileRepository(profile),
        scope = this,
        ioDispatcher = StandardTestDispatcher(testScheduler),
    )

    host.refresh()
    advanceUntilIdle()

    assertEquals(ProfileUiState(profile = profile), host.uiState.value)
}
```

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
- For Compose, verify rendering inputs are Compose `State` collected from observable state and that composables do not own business tasks or mutable business data.
- Verify each feature `Host` owns the observable state and asynchronous task boundary, remains independent of UI framework types, and receives test-controllable asynchronous dependencies.
- Separate persistent state from one-off effects, and define loading, empty, content, and failure states.
- Verify database reads use observable Flow from DAO methods, not one-shot queries; the UI reflects persisted state changes without manual refresh.
- Verify database writes go through a global event stream (`SharedFlow<DbEvent>`), not direct DAO calls from the Host or UI layer.
- Ensure the database writer executes on `Dispatchers.IO` and handles all sealed event subtypes exhaustively.
- Confirm database Flows are combined with other upstreams upstream of `flowOn(Dispatchers.Default)`, not on the UI thread.
- Test host state transitions, cancellation, and error propagation without a UI runtime; separately test that rendering receives UI-ready data without extra work.
