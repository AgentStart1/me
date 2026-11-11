# iOS 与 Swift Host

Host 不依赖 `UIView`、`UIViewController` 和 SwiftUI `View` 类型。使用注入的串行执行器或 actor 协调 Host，通过项目观察机制发布不可变状态和一次性副作用。

```swift
actor ProfileHost {
    private let repository: ProfileRepository
    private(set) var state = ProfileState()
    private var refreshGeneration = 0

    func refresh() async throws {
        refreshGeneration += 1
        let generation = refreshGeneration
        state = state.loading()
        let result: Result<Profile, Error>
        do {
            result = .success(try await repository.loadProfile())
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            result = .failure(error)
        }
        try Task.checkCancellation()
        guard generation == refreshGeneration else { return }
        state = state.reducing(result)
    }
}
```

- UIKit 和 SwiftUI 渲染保留在 `MainActor`，同时不让独立于框架的 Host 依赖 UI 类型。
- 阻塞或 CPU 密集工作通过注入的工作依赖执行，不在 `MainActor` 执行。
- 临时导航和呈现请求与持久状态分别建模。
- 随所属页面生命周期取消观察和 Host 管理的任务。
- actor 在跨越 `await` 时可重入。应用异步结果前，拒绝被取代的请求、取消先前工作，或串行执行完整操作。
