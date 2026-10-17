# Kotlin and Android

## Native terminology and choices

- Prefer `suspend` APIs, `coroutineScope`, `supervisorScope`, `withContext`, `Flow`,
  `Channel`, `Mutex`, `Semaphore`, `StateFlow`, `SharedFlow`, and existing application
  or lifecycle scopes. Choose supervision deliberately according to failure isolation.
- Prefer `val` and expressions such as `val x = if (a) b else c`. Read-only
  collection interfaces and `val` do not guarantee deep immutability.
- Avoid new designs around raw `Thread`, `thread`, `Runnable`, `HandlerThread`,
  `Executor`, `ExecutorService`, `Future`, or direct Java thread-pool management.
  Isolate required Java interop and define cancellation/shutdown behavior.
- Avoid `synchronized`, monitor locks, `wait`/`notify`/`notifyAll`, and `ReentrantLock`
  in coroutine paths. Prefer state ownership, actors, immutable snapshots,
  `Mutex.withLock`, or channels. Avoid suspending I/O inside state-update locks.
- Use `delay` rather than `Thread.sleep`. Move unavoidable blocking I/O to an
  appropriate dispatcher; use a CPU-appropriate dispatcher for computation.
- Keep `runBlocking` at a small synchronous boundary, such as a CLI entry point,
  legacy integration, or a test unable to use coroutine test APIs. Explain why a
  suspending interface is impractical; prefer `runTest` in coroutine tests.
- Rethrow `CancellationException` when mapping failures. `runCatching` catches it
  too. Switching dispatchers alone does not make arbitrary blocking calls cancellable.
- A lifecycle scope bounds task lifetime but does not prevent older requests from
  publishing after newer ones. Check identity/generation at the state owner's commit.

## State and documentation

Use sealed interfaces/classes with immutable variants and exhaustive `when`:

```kotlin
sealed interface LoadState<out T> {
    data object Idle : LoadState<Nothing>
    data object Loading : LoadState<Nothing>
    data class Success<T>(val value: T) : LoadState<T>
    data class Failure(val cause: Throwable) : LoadState<Nothing>
}
```

Use `Success<Result>` for a required non-null result; `Success<Result?>` only when
absence is a valid success. Publish snapshots via the existing state owner, for
example `StateFlow`; do not mutate objects behind a published snapshot.

Use KDoc links and `@param`, `@return`, or `@throws` only when they add a contract
beyond the signature. Document scope/dispatcher ownership and Flow collection
semantics where relevant. Verify with coroutine test schedulers and appropriate
unit/integration tests; Android lifecycle changes may also need Android tests.

## Callback and listener adaptation

Prefer an existing suspending API. For one-shot callback APIs, use
`suspendCancellableCoroutine` with cancellation cleanup and a race-safe, at-most-once
resume protocol; an `isActive` check alone is not atomic with resumption. Unregister
callbacks on cancellation and release any resource delivered after cancellation.
Use `callbackFlow` with `awaitClose` for repeated listeners; choose buffering and
handle failed `trySend` according to the event contract. Keep callback adapters at
the API boundary so the calling workflow reads as sequential suspending code.

Official reference: [Kotlin cancellation and timeouts](https://kotlinlang.org/docs/cancellation-and-timeouts.html).
