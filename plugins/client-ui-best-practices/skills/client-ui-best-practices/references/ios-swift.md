# iOS and Swift Host

Keep the Host independent of `UIView`, `UIViewController`, and SwiftUI `View` types. Use an injected serial executor or actor for Host coordination and publish immutable state and one-time effects through the project's observation mechanism.

```swift
actor ProfileHost {
    private let repository: ProfileRepository
    private(set) var state = ProfileState()

    func refresh() async {
        state = state.loading()
        let result: Result<Profile, Error>
        do {
            result = .success(try await repository.loadProfile())
        } catch {
            result = .failure(error)
        }
        state = state.reducing(result)
    }
}
```

- Keep UIKit and SwiftUI rendering on `MainActor` without making the framework-independent Host depend on UI types.
- Perform blocking or CPU-heavy work through injected worker dependencies rather than on `MainActor`.
- Model transient navigation and presentation requests separately from durable state.
- Cancel observation and Host-owned tasks with the owning screen lifecycle.
