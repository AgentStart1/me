# Python and asyncio

- In asyncio code prefer `async`/`await` and `asyncio.TaskGroup` when supported by
  the project's Python version (3.11+). For independently created tasks, retain an
  owner/reference, observe exceptions, and cancel and await them on shutdown.
- Propagate `asyncio.CancelledError` after cleanup in `finally` or a narrow handler.
  Swallowing it can break task-group and timeout behavior. Do not catch
  `BaseException` merely to convert failures into application state.
- Avoid `time.sleep`, blocking I/O, and thread locks on the event-loop thread.
  Use `asyncio.sleep`, async clients, and asyncio primitives. Use `asyncio.to_thread`
  for appropriate blocking I/O; choose processes or another suitable executor for
  CPU-bound work according to the interpreter/workload. Cancelling the await does
  not forcibly stop the worker thread.
- `asyncio.run` belongs at a synchronous entry boundary, not inside an already
  running loop. Use the project's async test integration for async tests.
- Prefer frozen dataclasses, tuples, and immutable snapshots where useful. Frozen
  dataclasses are shallow; their mutable members still require ownership.

Model states as a union of separate dataclasses, such as `Idle`, `Loading`,
`Success(value)`, and `Failure(cause)`. Put required data in constructors, use
`None` only for valid absence, and validate external inputs. Python annotations
and `match` do not themselves guarantee runtime type validity or exhaustive cases;
use the project's type checker and explicit unsupported-event handling.

Document ownership, cancellation, yielded values, and cleanup in docstrings.
Verify task cleanup, exception propagation, and stale completions using controlled
futures/events rather than wall-clock sleeps.

## Callback and listener adaptation

Prefer coroutine APIs. Bridge a one-shot callback with a loop-owned future and
await it. Schedule callbacks from other threads with `loop.call_soon_threadsafe`;
check and settle the future on its owning loop so cancellation or duplicate
completion cannot cause invalid-state errors. Unregister the callback in cleanup.
For repeated events use an async iterator or an owned `asyncio.Queue` with an
explicit capacity/overflow contract and shutdown path. Do not call `asyncio.run`
inside callbacks on the running loop to force sequential behavior.

Official reference: [asyncio coroutines and tasks](https://docs.python.org/3/library/asyncio-task.html).
