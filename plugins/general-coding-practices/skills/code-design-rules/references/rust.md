# Rust and Async Runtimes

- Reuse the project's async runtime. Own spawned tasks and observe their outcomes;
  dropping a Tokio `JoinHandle` detaches the task rather than cancelling it. Use
  task collections and the project's shutdown mechanism where appropriate.
- Cancellation commonly drops a future; verify cancellation safety of operations
  used in `select!` or timeouts. Drop does not roll back external side effects or
  provide asynchronous cleanup. Define an explicit shutdown/acknowledgment path
  for resources that need asynchronous cleanup.
- In Tokio, use async I/O, timers, and channels. Isolate blocking work with
  `spawn_blocking` or an appropriate pool; started blocking tasks cannot generally
  be aborted, so give long work a cooperative stop protocol when needed.
- Prefer ownership and message passing. A standard mutex can be appropriate for
  short critical sections without `.await`; use an async mutex only when the
  design needs it. Do not hold a blocking mutex guard across suspension.
- Prefer immutable bindings and enums carrying state-specific data. Borrow checking
  does not eliminate logical stale-result races; validate operation identity at
  publication. Interior mutability and shared ownership still need a clear contract.

```rust
enum LoadState<T, E> {
    Idle,
    Loading,
    Success(T),
    Failure(E),
}
```

Use exhaustive `match`. Use `Option<T>` inside `Success` only for legitimate
absence; avoid `unwrap` to repair an invalid state model. Use rustdoc (`///`) for
ownership, cancellation safety, panic/error behavior, and runtime requirements.
Verify shutdown and dropped-future behavior, owned task completion, and superseded
results with runtime-supported test controls.

## Callback and listener adaptation

Prefer a native future API. Bridge a one-shot callback with the runtime's oneshot
channel and await its receiver; transfer or guard the sender so only one callback
can complete it. Define cleanup when the receiver/future is dropped and release
resources from late callbacks. Use a stream or an owned channel for repeated
events, with a capacity/backpressure policy and unsubscribe/close behavior. Do not
block a runtime worker waiting for a callback to simulate an async return value.

Official reference: [Tokio graceful shutdown](https://tokio.rs/tokio/topics/shutdown).
