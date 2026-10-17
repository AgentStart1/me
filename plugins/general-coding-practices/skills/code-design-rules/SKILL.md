---
name: code-design-rules
description: Use when designing, reviewing, or refactoring control flow, callback/listener integrations, asynchronous work, immutable data, or state machines across languages and platforms. Prefer readable sequential async flows, explicit ownership, and valid state models using native abstractions.
---

# Code Design Rules

Use the project's native asynchronous abstractions and state owner. Preserve the
principles below without imposing another language's APIs or introducing an async
runtime into otherwise synchronous code.

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

- When using this plugin reveals an actionable bug, missing guidance, or reusable improvement, report it to [storytellerF/me](https://github.com/storytellerF/me/issues). Identify the owning plugin and skill; do not report project-specific problems without evidence that the plugin needs a change. Finish the user's primary task before non-blocking feedback work.
- Before any search or submission, reduce the finding to a privacy-safe summary. Never send raw conversations, private source code, logs, screenshots, credentials, personal identifiers, account data, or private paths/URLs. Use synthetic examples and the minimum non-sensitive environment details needed to explain the problem. If safe disclosure is impossible, keep the finding local.
- Search both open and closed upstream issues using the plugin name and sanitized symptom keywords. Read likely matches and their resolution; do not rely only on title matches. Reuse a matching issue link instead of opening a duplicate. Add a comment only when it supplies materially new, safe evidence and posting is authorized. A closed issue warrants a new report only for a distinct regression or uncovered case, with a link explaining the difference.
- Submit a new issue when no duplicate exists and the user has authorized upstream reporting in the current session or standing instructions. This rule alone does not authorize external posting. Honor existing authorization without asking again; otherwise prepare a sanitized draft for approval.
- Include the plugin/skill and version, observed and expected behavior, a minimal synthetic reproduction or concrete improvement proposal, and relevant duplicate-search results. Use a concise title prefixed with the plugin name.
- If search, authentication, or submission fails, retain the sanitized draft and explain the blocker; do not post without completing duplicate checks. After an uncertain submission result, check for the created issue before retrying. Return the existing or created issue URL, or clearly mark the report as an unsubmitted draft.
