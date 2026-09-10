---
name: client-ui-best-practices
description: Use for client UI implementation, review, or refactoring involving state ownership, event-loop or UI-thread work, lifecycle, asynchronous effects, or rendering in Android Views or Compose, iOS, React, desktop, and similar UI frameworks. Require a UI-framework-independent Host architecture on every supported platform.
context: fork
agent: client-ui-architecture-reviewer
---

# Client UI Best Practices

Keep rendering on the UI thread and put feature behavior in a UI-framework-independent `Host`. The UI observes immutable state, renders it, and invokes Host actions.

## UI boundary

- Reserve the UI or event-loop thread for short callbacks and framework-required rendering or view mutation.
- Move network, disk, database, parsing, cryptography, image processing, sorting, grouping, and other non-trivial work off the UI thread.
- Return to the UI thread only to render state or call an API that explicitly requires it. Background work must not update UI objects directly.
- Observe state and effects through lifecycle-aware subscriptions so views do not outlive their collectors.

## Host contract

Every feature Host must:

- Own feature state, one-time effects, actions, and asynchronous coordination.
- Avoid dependencies on UI widgets, view controllers, composables, components, or other framework-specific rendering types.
- Expose immutable state, a separate effect stream, and public user or lifecycle actions.
- Use an injected serial coordination executor owned by the application. Despite names such as `main`, this executor is not the platform UI thread.
- Confine Host state mutation and effect emission to that serial executor. Do not add locks or parallel mutations unless concurrent state access is an explicit requirement.
- Switch only blocking or CPU-intensive portions to appropriate worker executors, then resume Host coordination before changing state.
- Inject schedulers, clocks, and asynchronous dependencies that affect behavior so tests can control them.
- Provide deterministic cancellation owned by the screen, controller, presenter, or other component that owns the Host.

Platform-neutral shape:

```text
Host(dependencies, dispatchers):
    state  = observable immutable initialState
    effects = observable oneTimeEvents
    scope  = serialScope(dispatchers.coordination)

    action Refresh:
        scope.launch:
            state = state.with(loading = true)
            result = dispatchers.io.run { repository.load() }
            state = reduce(state, result)

    close:
        scope.cancel()
```

## State, effects, and work

- Publish durable render data as immutable state snapshots. Do not expose mutable collections or domain objects directly to the UI.
- Publish navigation, transient messages, permissions, and external actions through a separate one-time effect channel.
- Perform non-trivial observable transformations before values reach the UI subscriber and schedule them on the appropriate worker executor.
- Treat database reads as observable sources where supported. Route blocking writes through the Host command boundary or an existing application writer.
- Keep event handlers thin: translate framework events into Host actions instead of launching business work from rendering code.

## Platform references

Read only the reference for the target platform:

- Android Views or Compose with Kotlin: [`references/android-kotlin.md`](references/android-kotlin.md)
- iOS with Swift: [`references/ios-swift.md`](references/ios-swift.md)
- React: [`references/react.md`](references/react.md)
- Other desktop or event-loop frameworks: [`references/desktop.md`](references/desktop.md)

## Verification

- Test Host state transitions, effects, errors, cancellation, ordering, and scheduler selection without a UI runtime.
- Use UI tests for rendering, event wiring, lifecycle integration, and accessibility.
- Verify both directions: expensive work stays off the UI thread, and background work never mutates UI objects.
- Use platform diagnostics or profiler evidence when investigating UI stalls.
