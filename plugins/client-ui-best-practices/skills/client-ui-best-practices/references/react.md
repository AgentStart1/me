# React Host

Keep the Host independent of React components and hooks. Components subscribe to immutable Host snapshots and dispatch actions; they do not own feature business logic.

```typescript
interface ProfileHost {
  getSnapshot(): ProfileState
  subscribe(listener: () => void): () => void
  refresh(): Promise<void>
  close(): void
}

function ProfileScreen({ host }: { host: ProfileHost }) {
  const state = useSyncExternalStore(
    listener => host.subscribe(listener),
    () => host.getSnapshot(),
  )
  return <ProfileView state={state} onRefresh={() => void host.refresh()} />
}
```

- Use `useSyncExternalStore` or the project's equivalent adapter to bridge Host state into rendering.
- Keep effects in a separate consumable channel rather than encoding transient events as durable render state.
- Do not perform expensive transformations during render; compute them in the Host or a worker.
- Tie subscriptions and cancellation to component ownership and unmounting.
