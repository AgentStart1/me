---
name: kotlin-project-rules
description: Use for Kotlin or Android Kotlin work involving .kt files, coroutines, concurrency, tests, or bug fixes to choose coroutine-first designs, prefer immutable vals and expressions over var mutation, and avoid Java threads, blocking, locks, synchronized, wait/notify, or Executor-style concurrency.
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
