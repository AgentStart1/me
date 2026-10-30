---
name: code-design-rules
description: Use when implementing, debugging, reviewing, or refactoring control flow, callback/listener integrations, asynchronous resource ownership, immutable data, or state machines across languages and platforms.
---

# Code Design Rules

Use the project's native asynchronous abstractions and state owner. Preserve the
principles below without imposing another language's APIs or introducing an async
runtime into otherwise synchronous code.

## Project independence

Express the design in project-owned interfaces and normal library/framework dependencies. Do not introduce runtime checks, imports, configuration keys or abstractions tied to this AI plugin's identity, installed path or execution environment merely to apply its guidance. Legitimate compiler/build plugins and runtime libraries remain normal project dependencies; add them when the design requires them, independently of the AI skill.

## Platform references

Read only the references relevant to the changed code. For mixed-platform work,
apply each reference at its own boundary.

| Language or platform | Reference |
| --- | --- |
| Kotlin, Android Kotlin | [Kotlin and Android](references/kotlin.md) |
| Swift, Apple platforms | [Swift](references/swift.md) |
| TypeScript, JavaScript, browser or Node.js | [TypeScript and JavaScript](references/typescript-javascript.md) |
| Python, asyncio | [Python](references/python.md) |
| Rust, Tokio | [Rust](references/rust.md) |
| C#, .NET | [C# and .NET](references/csharp.md) |

For other languages, map the same principles to their existing task, cancellation,
synchronization, and data-model facilities. Do not assume every runtime provides
structured concurrency or exhaustive tagged unions.

## Structural fixes before compensating logic

- Prefer correcting ownership, lifecycle, state representation, or an interface
  boundary at the root cause before adding another retry, flag, fallback, special
  case, or cleanup patch. Choose the smallest structural change that removes the
  invalid state; do not introduce a general framework without a concrete need.
- Give resources and state transitions one clear owner. Distinguish scoped work
  that must stop on exit from persistent work whose ownership must be explicitly
  transferred. Keep platform behavior behind a narrow adapter with the same contract.
- Preserve recovery for failures that structure cannot eliminate: crashes, partial
  publication, uncertain external effects, and lost connectivity. Keep ownership
  evidence until cleanup is confirmed; do not mistake fewer branches for safety.
- Verify the ownership and publication invariants at failure and cancellation
  boundaries, including late completion and interrupted handoff. When a workaround
  remains necessary, record its cause, scope, and removal condition near the boundary.

## Sequential asynchronous control flow

- Express dependent asynchronous operations as a readable sequence using native
  suspension/await facilities, with results and error handling near their use.
  Prefer an existing async API over nested callbacks, listener-driven continuation
  chains, or state spread across unrelated handlers.
- At callback-only boundaries, adapt one-shot operations to one awaitable result.
  Handle success, failure, cancellation, synchronous completion, and duplicate or
  late callbacks. Complete at most once and release registrations/resources on all
  terminal paths. Connect cancellation to the underlying API when supported;
  otherwise prevent late completion from publishing state.
- Adapt repeated events to a stream, async sequence/iterator, or the project's
  existing event abstraction. Define subscription ownership, buffering/backpressure,
  errors, completion, and unsubscription; do not treat a multi-shot listener as a
  single result. Preserve framework callbacks at their required entry boundaries.
- Sequential source code does not mean blocking execution. Avoid synchronous waits
  used to imitate suspension. Keep independent work concurrent when appropriate,
  and retain its owner, error, and cancellation semantics.

## Task ownership and concurrency

- Prefer structured concurrency where supported. Give every asynchronous task an
  explicit owner and lifetime; collect failures and cancel or join owned work on
  shutdown. Background work that outlives a request needs a longer-lived owner.
- Prefer native asynchronous I/O, scheduling, and non-blocking synchronization in
  async paths. Avoid sleeping, busy waiting, blocking bridges, or manual thread
  management on event loops, UI threads, and cooperative executors.
- Match execution to the workload. CPU-bound or unavoidable blocking work may
  need a worker, process, dispatcher, or bounded pool. Keep platform interop behind
  a small boundary with explicit cancellation, shutdown, and resource ownership.
  Cancelling an await does not necessarily stop the underlying operation.
- Preserve cancellation when translating failures into results or state. Do not
  report cancellation as an ordinary failure or continue obsolete side effects.
  Use the runtime's cleanup mechanism; bound any intentionally uncancellable cleanup.
- Prefer one state owner, immutable snapshots, or message passing before adding
  shared mutation. Where locking is needed, choose a primitive appropriate to the
  runtime and keep critical sections small. Do not hold a lock across suspension
  unless the design explicitly requires it and the primitive supports it.
- Serial execution between suspension points does not serialize an entire async
  operation. At publication, reject completions superseded by a newer request or
  transition, using request identity, a generation, or the owner's existing mechanism.

## Immutable values and state models

- Prefer immutable bindings, values, and expression-oriented construction where
  idiomatic. Restrict mutation to the owner that needs it. A constant binding does
  not make the referenced object or collection deeply immutable.
- When data is required only in certain states, use variants carrying their own
  required values: sealed types, associated-value enums, discriminated unions, or
  the closest native model. Avoid independent flags and nullable fields that admit
  invalid combinations. In dynamic languages, validate variants at boundaries.
- Keep optional values for genuinely optional data within a valid state. Avoid
  forced unwraps, placeholder values, or defaults that hide a broken invariant.
- For workflows whose legal operations depend on state, define states, events,
  allowed transitions, and handling of unsupported events. Reuse an existing state
  machine or a small pure transition function; do not require a framework.
- Publish one immutable snapshot per transition through the existing state owner,
  so consumers cannot observe new status paired with stale or missing data.

For example, model `Idle | Loading(requestId) | Success(value) | Failure(cause)`.
Only `Success` carries the result, and it always carries one. Make its value optional
only if a successful result may legitimately be absent. Define whether cancellation
restores an earlier state or enters a separate state according to the workflow.

## Contracts and verification

- Use the platform's API documentation convention for public APIs and non-obvious
  contracts. Document units, ranges, ownership, lifecycle, cancellation, execution
  context, failure behavior, and stream/subscription semantics when callers need
  them. Avoid boilerplate that repeats the signature; keep docs aligned with code.
- After concurrency changes, verify cancellation propagation, execution context,
  cleanup, and error propagation. After state changes, verify valid transitions,
  unsupported events, required data, and superseded completions. Prefer deterministic
  schedulers or controlled completions over timing-dependent sleeps.

## Upstream improvement feedback

- Report actionable plugin bugs or reusable improvements to [storytellerF/me](https://github.com/storytellerF/me/issues), identifying the plugin and skill. Exclude project-only problems without evidence of a plugin defect. Finish the primary task before non-blocking feedback work.
- Before searching or posting, reduce evidence to a minimal privacy-safe summary or synthetic reproduction. Never disclose raw conversations, private code, logs, screenshots, credentials, personal/account data, or private paths/URLs. Keep findings local if safe disclosure is impossible.
- Search open and closed issues and read likely matches and resolutions. Reuse matching reports; a distinct regression or uncovered case may need a linked new issue. Posting a new issue or a materially useful comment requires existing user authorization; this rule grants none. Without authorization, prepare an unsubmitted draft.
- Include the plugin/skill version, observed and expected behavior, reproduction or proposal, and duplicate-search results; prefix new issue titles with the plugin name. On access or submission failure, retain the draft and explain the blocker. After an uncertain submission, check whether it succeeded before retrying. Return the report link or clearly label the draft as unsubmitted.
