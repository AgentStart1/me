# TypeScript and JavaScript

- Use promises and `async`/`await` with an explicit request/component/service owner.
  Promises are not structured task scopes. `Promise.all` rejection neither cancels
  sibling operations nor waits for their cleanup; define that behavior explicitly.
- Pass an `AbortSignal` to supporting APIs. Aborting is cooperative and does not
  cancel an arbitrary promise or roll back side effects. At publication, check that
  the operation still belongs to the active request, even when abort is available.
- Do not classify every rejection as a failure after cancellation. Respect the
  API's abort contract and the owner's signal; abort reasons are not always an
  `Error` named `AbortError`. Clean up timers, subscriptions, and event listeners.
- Keep blocking I/O, busy waits, and heavy computation off the event loop. Use
  asynchronous I/O and workers or a suitable pool for expensive computation.
- Prefer `const`, `readonly` fields/collections, and immutable update patterns.
  `const` fixes the binding; TypeScript `readonly` is a compile-time restriction,
  and shallow copies/freezing do not establish deep immutability.

```typescript
type LoadState<T> =
  | { readonly kind: "idle" }
  | { readonly kind: "loading" }
  | { readonly kind: "success"; readonly value: T }
  | { readonly kind: "failure"; readonly cause: unknown };
```

Use discriminated unions and an exhaustive `switch`/`never` check in TypeScript.
In JavaScript use tagged objects and validate required fields at boundaries; JSDoc
can document variants but does not enforce them at runtime. Publish complete
snapshots through the existing store/reducer/owner. Document cancellation and
subscription contracts with JSDoc/TSDoc. Verify with controlled promises and fake
timers, including completion after disposal and out-of-order requests.

## Callback and listener adaptation

Prefer native promise APIs. Wrap a one-shot callback with a promise only at the
integration boundary; settle it once and explicitly release listeners/resources.
Promise settlement alone does not stop late callbacks from performing side effects.
Wire an `AbortSignal` where supported, including an already-aborted signal, and
remove abort/event listeners at completion. Model repeated events with an async
iterable or the existing stream abstraction, with bounded buffering or a defined
overflow policy and cleanup on early iteration exit. Keep DOM/framework handlers
as entrypoints that call a coherent async workflow.

References: [AbortController](https://developer.mozilla.org/en-US/docs/Web/API/AbortController),
[TypeScript discriminated unions](https://www.typescriptlang.org/docs/handbook/2/narrowing.html#discriminated-unions).
