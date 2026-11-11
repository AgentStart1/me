# Python 与 asyncio

- asyncio 代码优先使用 `async`/`await`；项目 Python 版本支持时（3.11+），使用 `asyncio.TaskGroup`。独立创建的任务应保留管理者或引用、观察异常，并在关闭时取消并等待其结束。
- 在 `finally` 或范围明确的处理函数中完成清理后，继续传播 `asyncio.CancelledError`。吞掉该异常可能破坏任务组和超时行为。不要仅为将失败转换成应用状态而捕获 `BaseException`。
- 事件循环线程上避免 `time.sleep`、阻塞 I/O 和线程锁。使用 `asyncio.sleep`、异步客户端和 asyncio 同步原语。适合的阻塞 I/O 可使用 `asyncio.to_thread`；CPU 密集型工作应根据解释器和负载选择进程或其他适当执行器。取消 await 不会强制停止工作线程。
- `asyncio.run` 应位于同步入口边界，不应放入已经运行的事件循环。异步测试使用项目已有的异步测试集成。
- 合适时优先使用冻结 dataclass、元组和不可变快照。冻结 dataclass 仅是浅层限制，其可变成员仍需明确管理责任。

将状态建模为独立 dataclass 的联合，例如 `Idle`、`Loading`、`Success(value)` 和 `Failure(cause)`。必需数据通过构造函数传入，只有缺失合法时才使用 `None`，并验证外部输入。Python 类型注解和 `match` 本身不保证运行时类型有效或分支穷尽；使用项目的类型检查器，并显式处理不支持的事件。

在 docstring 中说明管理责任、取消、产出的值和清理。通过受控 future 或 event 验证任务清理、异常传播和过时结果，避免依赖实际时间的休眠。

## 回调与监听器适配

优先使用协程 API。单次回调用事件循环管理的 future 桥接，并等待其结果。其他线程发起的回调通过 `loop.call_soon_threadsafe` 调度；在 future 所属事件循环上检查和结算，避免取消或重复完成导致无效状态错误。清理时注销回调。重复事件使用异步迭代器或有明确管理者的 `asyncio.Queue`，定义容量、溢出约定和关闭路径。不要在运行中的事件循环回调内调用 `asyncio.run` 来强行实现顺序行为。

官方参考：[asyncio 协程与任务](https://docs.python.org/3/library/asyncio-task.html)。
