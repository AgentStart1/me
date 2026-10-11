---
name: kotlin-project-rules
description: Use for Kotlin or Android Kotlin work involving .kt files, state models, coroutines, concurrency, tests, or bug fixes to choose coroutine-first designs, prefer immutable vals and expressions, model state-dependent data with sealed types and state machines, and avoid Java blocking concurrency primitives.
---

# Kotlin Project Rules

For Kotlin project work, make concurrency design decisions coroutine-first. Prefer structured concurrency and project-provided coroutine scopes over Java thread-model primitives, blocking bridges, and manual synchronization.

## Rules

- Prefer `suspend` APIs, `coroutineScope`, `supervisorScope`, `withContext`, `Flow`, `Channel`, `Mutex`, `Semaphore`, `StateFlow`, `SharedFlow`, or an existing application/lifecycle scope.
- Reduce `var` usage. Prefer immutable `val` declarations and expression-oriented code, such as `val x = if (a) b else c`, instead of declaring a mutable variable and assigning it across branches.
- Avoid designing new code around `runBlocking`. Use it only at clear synchronous boundaries, such as a CLI `main` bridge, a test body that cannot use coroutine test APIs, or legacy integration glue. Keep the scope small and explain why a suspending API is not practical.
- Avoid raw `Thread`, `thread { ... }`, `Runnable`, `HandlerThread`, manual thread lifecycle management, `Executor`, `ExecutorService`, `Future`, and direct Java thread-pool APIs for new Kotlin code. Prefer coroutines with an appropriate dispatcher or the concurrency abstraction already used by the project.
- Avoid `synchronized`, monitor locks, `wait`, `notify`, `notifyAll`, `ReentrantLock`, and other Java blocking synchronization primitives. Prefer coroutine-friendly state ownership, immutable snapshots, actors, `Mutex.withLock`, `StateFlow`, or `Channel`.
- Avoid `Thread.sleep` and blocking waits. Prefer `delay`, suspending APIs, timeouts, or coroutine test scheduler controls.
- If a platform or third-party API requires Java threading or synchronization, isolate it behind a small boundary, keep the rest of the Kotlin code coroutine-based, define cancellation/shutdown behavior, and add tests for lifecycle behavior.
- After changing coroutine or concurrency behavior, run the relevant unit, integration, or Android tests that cover cancellation, dispatcher selection, lifecycle cleanup, and error propagation.

## State modeling and nullability

- When a value is required only in certain states, model those states with a `sealed interface` or `sealed class` and immutable variants. Put required non-null values on the variants that need them instead of combining an enum or Boolean flags with nullable fields in one shared object. Make invalid state/data combinations unrepresentable.
- Keep nullable properties for genuinely optional data within a valid state. Do not replace state modeling with `!!`, repeated null checks, placeholder values, or defaults that hide a missing state invariant.
- Model workflows with a state machine when legal operations or transitions depend on the current state. Define states, events, and allowed transitions explicitly; use exhaustive `when` expressions over sealed types and define how unsupported events are handled. Reuse the project's existing state-machine abstraction when appropriate; a small pure transition function is sufficient for simple workflows.
- Publish one immutable state snapshot per transition through the existing state owner so consumers cannot observe a new state paired with stale or missing data. For asynchronous work, use the project's coroutine-friendly ownership mechanism and reject stale completions when a newer transition has superseded them.
- When changing state behavior, verify allowed transitions, unsupported events, and the data invariants of each state, including cancellation or stale completion handling when applicable.

For example, loading has no result yet, while success always contains a result:

```kotlin
sealed interface LoadState<out T> {
    data object Idle : LoadState<Nothing>
    data object Loading : LoadState<Nothing>
    data class Success<T>(val value: T) : LoadState<T>
    data class Failure(val cause: Throwable) : LoadState<Nothing>
}
```

Use `Success<Result>` when the result must be non-null; use `Success<Result?>` only when a successful result may legitimately be absent. Consumers access `value` in the `Success` branch rather than checking an unrelated nullable field.

## KDoc

- Use KDoc for public Kotlin APIs and non-obvious contracts. Describe behavior and caller obligations rather than repeating the declaration; omit boilerplate for straightforward internal declarations.
- Document units, valid ranges, state ownership, lifecycle, and failure behavior when relevant. For coroutine APIs, explain cancellation behavior, scope ownership, dispatcher or thread requirements, and Flow collection semantics when callers need that information.
- Use links to declarations and add `@param`, `@return`, or `@throws` only when they provide information beyond the signature. Keep KDoc synchronized with implementation changes and follow the project's documentation language and style.
