# iOS and Swift Host

Keep the Host independent of `UIView`, `UIViewController`, and SwiftUI `View` types. Use an injected serial executor or actor for Host coordination and publish immutable state and one-time effects through the project's observation mechanism.

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

- Keep UIKit and SwiftUI rendering on `MainActor` without making the framework-independent Host depend on UI types.
- Perform blocking or CPU-heavy work through injected worker dependencies rather than on `MainActor`.
- Model transient navigation and presentation requests separately from durable state.
- Cancel observation and Host-owned tasks with the owning screen lifecycle.
- Actors are reentrant across `await`. Reject superseded requests, cancel prior
  work, or serialize complete operations before applying an asynchronous result.
