# TypeScript 与 JavaScript

- 使用 promise 和 `async`/`await`，明确由请求、组件或服务管理任务。promise 本身不是结构化任务作用域。`Promise.all` 拒绝时，既不会取消同级操作，也不会等待其清理；必须明确定义这些行为。
- 向支持的 API 传递 `AbortSignal`。中止是协作式的，不会取消任意 promise 或回滚副作用。发布结果时，即使支持中止，也要检查操作是否仍属于当前请求。
- 取消后，不要将所有拒绝都归为失败。遵循 API 的中止约定和管理者的信号；中止原因并不总是名为 `AbortError` 的 `Error`。清理计时器、订阅和事件监听器。
- 阻塞 I/O、忙等待和重计算不能占用事件循环。使用异步 I/O，昂贵计算交给 worker 或适当的执行池。
- 优先使用 `const`、`readonly` 字段或集合，以及不可变更新方式。`const` 只固定绑定；TypeScript 的 `readonly` 是编译期限制，浅复制或浅冻结也不构成深度不可变。

```typescript
type LoadState<T> =
  | { readonly kind: "idle" }
  | { readonly kind: "loading" }
  | { readonly kind: "success"; readonly value: T }
  | { readonly kind: "failure"; readonly cause: unknown };
```

TypeScript 使用可辨识联合类型和穷尽的 `switch`/`never` 检查。JavaScript 使用带标签的对象，并在边界验证必需字段；JSDoc 可以描述变体，但不会在运行时强制执行。通过已有 store、reducer 或管理者发布完整快照。用 JSDoc/TSDoc 记录取消和订阅约定。使用受控 promise 和模拟计时器验证，包括释放后才完成以及请求乱序的情况。

## 回调与监听器适配

优先使用原生 promise API。只在集成边界将单次回调封装为 promise；只结算一次，并显式释放监听器和资源。promise 已结算并不会阻止迟到的回调产生副作用。支持时接入 `AbortSignal`，包括信号已中止的情况，并在完成时移除中止和事件监听器。重复事件使用异步可迭代对象或现有流抽象，限定缓冲容量或定义溢出策略，并在提前退出迭代时清理。DOM 和框架处理函数保留为入口，调用连贯的异步流程。

参考：[AbortController](https://developer.mozilla.org/en-US/docs/Web/API/AbortController)、[TypeScript 可辨识联合类型](https://www.typescriptlang.org/docs/handbook/2/narrowing.html#discriminated-unions)。
