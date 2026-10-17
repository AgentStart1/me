# C# and .NET

- Prefer `Task`/`Task<T>`, `async`/`await`, asynchronous I/O, and the project's
  request/service lifetime. Pass `CancellationToken` through supporting calls.
  Tasks do not automatically form a structured parent-child lifetime; own and
  observe background work, including shutdown.
- `Task.WhenAll` observes completion but does not cancel siblings when one fails.
  Coordinate linked cancellation explicitly when the workflow requires it.
- Preserve `OperationCanceledException` for the relevant cancellation token when
  translating exceptions. Do not turn request shutdown into ordinary failure.
  Dispose owned cancellation sources and release resources in `finally` or with
  `using`/`await using` as appropriate.
- Avoid `.Result`, `.Wait()`, `Thread.Sleep`, and blocking locks on async/UI paths.
  Prefer awaited APIs, `Task.Delay`, `SemaphoreSlim.WaitAsync`, or channels. `lock`
  remains appropriate for small synchronous critical sections; do not await within it.
- Use `Task.Run` for appropriate CPU work, not as a replacement for asynchronous
  I/O. Cancellation of an await does not forcibly stop arbitrary blocking code.
- Prefer immutable records and immutable collections where useful. `readonly`,
  `init`, and records do not deeply freeze mutable objects they reference.

Use a closed variant model where supported, or an abstract record with controlled
derived variants and construction. Put `Value` only on `Success<T>` and `Cause`
only on failure; nullable reference annotations do not enforce runtime invariants.
Do not assume a record hierarchy gives exhaustive compiler checks on every
supported language version; explicitly handle unsupported states/events.

Use XML documentation comments for cancellation-token ownership, execution-context
requirements, errors, and disposal contracts. Verify cancellation versus failure,
cleanup, UI context, and out-of-order results with controlled task completions.

## Callback and event adaptation

Prefer task-based APIs. Adapt one-shot events/callbacks with
`TaskCompletionSource<T>` using `RunContinuationsAsynchronously` where appropriate,
`TrySetResult`/`TrySetException`/`TrySetCanceled` for racing terminal paths, and an
owned cancellation registration. Handle cancellation before event registration;
unsubscribe and dispose registrations on completion, including synchronous callbacks.
For repeated events use `IAsyncEnumerable<T>` or `Channel<T>` with explicit capacity,
overflow/backpressure, and disposal semantics. Keep `async void` at framework-required
event handlers and handle their errors there; internal workflows should return tasks.

Official reference: [.NET task cancellation](https://learn.microsoft.com/en-us/dotnet/standard/parallel-programming/task-cancellation).
