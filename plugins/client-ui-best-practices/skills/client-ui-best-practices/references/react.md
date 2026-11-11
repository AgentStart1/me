# React Host

Host 不依赖 React 组件和 hook。组件订阅 Host 的不可变快照并分发操作，不管理功能业务逻辑。

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

- 使用 `useSyncExternalStore` 或项目等效适配层，将 Host 状态接入渲染。
- 副作用使用独立的可消费通道，不将临时事件编码为持久渲染状态。
- 不在渲染期间执行昂贵转换；交给 Host 或 worker 计算。
- 将订阅和取消与组件管理责任及卸载关联。
- 单个 JavaScript 事件循环不会让完整异步请求串行化。通过中止信号和／或请求标识，防止已被取代的完成结果覆盖当前快照；不要将取消发布为错误。
