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

## Kotlin/Android default

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
- Inspect observable pipelines as well as callbacks: ensure non-trivial `map` and related Flow operators execute upstream of an appropriate `flowOn` (or an equivalent background scheduler).
- Verify cancellation follows the screen, ViewModel, or feature lifecycle.
- Ensure a background result cannot update a destroyed or inactive UI directly; publish state and let lifecycle-aware observation render it.
- Separate persistent state from one-off effects, and define loading, empty, content, and failure states.
- Test state transitions, cancellation, error propagation, and that rendering receives UI-ready data without extra work.
