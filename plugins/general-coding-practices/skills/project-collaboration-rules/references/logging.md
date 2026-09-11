# Diagnostic Logging

## Inspect existing conventions

- Find the project's logger, log-level configuration, formatting conventions, and redaction helpers before editing code.
- Search nearby code for comparable events and reuse established event names and fields.
- Identify operation boundaries, failure paths, state transitions, and external calls that need diagnosis. Do not add logs merely because a line is important.

## Select meaningful events

- Log stable start or completion events for significant operations when timing or outcome matters.
- Log network, database, file, queue, subprocess, or device boundaries with operation, outcome, useful duration, and retry attempt.
- Log meaningful state transitions and lifecycle milestones, especially when an operation can stall, retry, cancel, or fail.
- Use `warn` for recoverable unexpected conditions and `error` for terminal failures, including the exception and stable diagnostic context.
- Reserve `debug` or `trace` for high-volume diagnostic details. Avoid every loop iteration, UI render, recomposition, adapter bind, poll, or ordinary accessor.

## Structure and protect data

- Prefer structured fields over concatenated prose. Reuse stable names such as `operation`, `component`, `outcome`, `duration_ms`, `attempt`, and existing correlation identifiers.
- Keep event messages concise and stable. Do not use user-provided text as an event name.
- Never log passwords, access tokens, API keys, cookies, authorization headers, secrets, private keys, raw credentials, or complete request and response bodies without an approved redaction-safe path.
- Treat personal data, payment data, device identifiers, location, and user-generated content as sensitive. Log safe classifications, counts, approved hashes, or redacted identifiers instead.
- Apply existing sanitization helpers. If none exist, add only the smallest local sanitization needed and document the assumption.

## Place logs at the owning boundary

- Log an error where the code has enough context to act or report the final failure. Avoid logging the same exception at every layer.
- Use identifiers already propagated by the project; do not invent identifiers that cannot connect related events.
- Do not change control flow, retry policy, exception handling, or user-visible behavior solely to emit a log.
- Logging must not throw, block critical paths, do unbounded work, or eagerly serialize large payloads. Use supported lazy logging or level guards for expensive diagnostics.
- In UI code, log user-visible actions, failed loads, and meaningful lifecycle transitions, not render passes or every state emission.
