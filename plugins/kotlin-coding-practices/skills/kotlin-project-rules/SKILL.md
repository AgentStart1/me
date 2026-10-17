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
- Rethrow `CancellationException` when translating coroutine exceptions into result
  or UI state. `runCatching` catches cancellation too; do not turn it into an error
  state or continue device/network work after the owning scope was cancelled.
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

## Upstream improvement feedback

- When using this plugin reveals an actionable bug, missing guidance, or reusable improvement, report it to [storytellerF/me](https://github.com/storytellerF/me/issues). Identify the owning plugin and skill; do not report project-specific problems without evidence that the plugin needs a change. Finish the user's primary task before non-blocking feedback work.
- Before any search or submission, reduce the finding to a privacy-safe summary. Never send raw conversations, private source code, logs, screenshots, credentials, personal identifiers, account data, or private paths/URLs. Use synthetic examples and the minimum non-sensitive environment details needed to explain the problem. If safe disclosure is impossible, keep the finding local.
- Search both open and closed upstream issues using the plugin name and sanitized symptom keywords. Read likely matches and their resolution; do not rely only on title matches. Reuse a matching issue link instead of opening a duplicate. Add a comment only when it supplies materially new, safe evidence and posting is authorized. A closed issue warrants a new report only for a distinct regression or uncovered case, with a link explaining the difference.
- Submit a new issue when no duplicate exists and the user has authorized upstream reporting in the current session or standing instructions. This rule alone does not authorize external posting. Honor existing authorization without asking again; otherwise prepare a sanitized draft for approval.
- Include the plugin/skill and version, observed and expected behavior, a minimal synthetic reproduction or concrete improvement proposal, and relevant duplicate-search results. Use a concise title prefixed with the plugin name.
- If search, authentication, or submission fails, retain the sanitized draft and explain the blocker; do not post without completing duplicate checks. After an uncertain submission result, check for the created issue before retrying. Return the existing or created issue URL, or clearly mark the report as an unsubmitted draft.
