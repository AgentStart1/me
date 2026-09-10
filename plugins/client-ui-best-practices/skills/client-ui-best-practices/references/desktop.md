# Desktop and Event-loop Hosts

Keep the Host independent of windows, controls, scenes, and toolkit event objects. Adapt its immutable state and one-time effects at the UI boundary.

- Give the Host an injected serial coordination executor that is distinct from the toolkit UI dispatcher.
- Perform blocking and CPU-heavy work on injected worker executors.
- Marshal only rendering and toolkit-required calls onto the UI dispatcher.
- Dispose subscriptions and cancel Host work when the owning window or screen closes.
- Test the Host with deterministic executors without starting the desktop UI runtime.

Apply the same boundary to Swing/JavaFX, Compose Desktop, .NET desktop frameworks, Qt, Electron, and similar single-event-loop toolkits while using their native lifecycle and scheduling APIs at the adapter layer.
