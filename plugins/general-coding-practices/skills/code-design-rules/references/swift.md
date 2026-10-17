# Swift and Apple Platforms

- Prefer `async`/`await`, `async let`, and task groups for owned concurrent work.
  An unstructured `Task` needs explicit ownership and cancellation; do not treat
  `Task.detached` as a child with inherited lifecycle or actor isolation.
- Use actors or the existing isolated owner for shared state. `@MainActor` applies
  to UI-bound state, not all computation. An actor can process other work while an
  operation suspends: recheck request identity before committing a result.
- Cancellation is cooperative. Propagate `CancellationError`, use
  `Task.checkCancellation()` when appropriate, and handle cancellation from APIs
  that represent it through other error types. Do not convert owner cancellation
  into an ordinary error state.
- Avoid `Thread.sleep`, semaphore waits, and blocking queue bridges on cooperative
  executors. Use asynchronous APIs and `Task.sleep`; isolate unavoidable blocking
  interop on an appropriate bounded executor rather than assuming `Task` offloads it.
- Prefer `let`, value types, and enums with associated values. `let` does not freeze
  an instance of a mutable class. Use `Sendable` according to isolation contracts;
  do not silence violations with unchecked conformance without a proven boundary.

```swift
enum LoadState<Value> {
    case idle
    case loading
    case success(Value)
    case failure(any Error)
}
```

Use exhaustive `switch` handling. Only use `Value?` in success when absence is
valid. Describe ownership, isolation, cancellation, and errors in documentation
comments (`///`, with Parameters/Returns/Throws when useful). Verify cancellation,
actor reentrancy, superseded completions, and task cleanup with controlled async tests.

## Callback and delegate adaptation

Prefer native async APIs. Wrap a one-shot completion handler with a checked
continuation, resuming exactly once on success or failure. A checked continuation
does not automatically propagate task cancellation: coordinate registration,
cancellation, and completion with a race-safe owner, including cancellation before
registration. For repeated delegate/listener events use `AsyncStream` or
`AsyncThrowingStream`, with termination cleanup and an explicit buffering policy.
Keep required delegates as adapters rather than spreading workflow logic among them.

Official reference: [Swift concurrency](https://docs.swift.org/swift-book/documentation/the-swift-programming-language/concurrency/).
