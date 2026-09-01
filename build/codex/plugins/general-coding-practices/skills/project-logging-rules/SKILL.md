---
name: project-logging-rules
description: Use when implementing, reviewing, or debugging project code that needs diagnostic logging for lifecycle events, state transitions, external I/O, retries, handled errors, or performance investigations. Add necessary, structured, privacy-safe logs while following the project's existing logging framework and runtime configuration.
---

# Project Logging Rules

Add logs that make important behavior diagnosable in production and during development without turning normal execution into noise. Preserve the project's existing logging conventions and keep logging separate from business behavior.

## Workflow

### 1. Inspect before adding logs

- Find the project's logger, log-level configuration, formatting conventions, and redaction helpers before editing code.
- Search nearby code for comparable events and reuse established event names and fields.
- Identify the operation boundaries, failure paths, state transitions, and external calls that need diagnosis. Do not add logs merely because a line of code is important.

### 2. Select meaningful events

- Log a stable event at the start or completion of a significant operation when timing or outcome matters.
- Log external boundaries such as network, database, file, queue, subprocess, or device calls with operation, outcome, duration when useful, and attempt number for retries.
- Log meaningful state transitions and lifecycle milestones, especially when an operation can stall, retry, or be cancelled.
- Log recoverable unexpected conditions at `warn` (or the project's equivalent) and terminal failures at `error` with the exception/stack trace and stable diagnostic context.
- Use `debug`/`trace` only for high-volume details needed during diagnosis. Avoid logging every loop iteration, UI render/recomposition, adapter bind, poll, or ordinary accessor.

### 3. Structure and protect log data

- Prefer structured key/value fields over concatenated prose. Use stable names such as `operation`, `component`, `outcome`, `duration_ms`, `attempt`, `request_id`, and a redacted entity identifier where the project supports them.
- Keep event messages stable and concise so operators can search and aggregate them. Do not use user-provided text as an event name.
- Never log passwords, access tokens, API keys, cookies, authorization headers, secrets, private keys, raw credentials, or complete request/response bodies unless the project has an explicit, approved redaction-safe diagnostic path.
- Treat personal data, payment data, device identifiers, location data, and user-generated content as sensitive. Log a safe classification, count, hash approved by the project, or redacted identifier instead of the value.
- Apply existing sanitization/redaction helpers before logging. If none exist, add the smallest local sanitization needed and document the assumption in the change.

### 4. Place logs at the right boundary

- Prefer logging an error where the code has enough context to act on it or report the final failure. Avoid logging the same exception at every layer.
- Include correlation, request, job, or operation identifiers when the project already propagates them; do not invent identifiers that cannot connect related events.
- Do not change control flow, retry policy, exception handling, or user-visible behavior solely to emit a log.
- Logging must not throw, block critical paths, perform unbounded work, or eagerly serialize large payloads. Guard expensive diagnostic construction with the project's supported level check or lazy logging API.
- In UI code, log user-visible actions, failed loads, and meaningful screen/lifecycle transitions—not render passes or every state emission.

### 5. Verify the change

- Run the narrowest relevant tests, formatter, lint, typecheck, and build checks configured by the project.
- Exercise or inspect success, handled-failure, retry/timeout, cancellation, and empty-input paths when they are in scope.
- Check the diff for sensitive values, duplicated error logs, noisy loops, accidental stdout printing, and inconsistent field names or log levels.
- If the project has log-capture tests or an observability contract, update focused assertions for event name, level, and safe fields. Do not make incidental log wording a test contract.

## Completion checklist

- [ ] Existing logging and redaction conventions were inspected and reused.
- [ ] Each new log answers a concrete diagnostic question.
- [ ] Levels, fields, identifiers, and event names are consistent with the project.
- [ ] Sensitive data and high-volume noise are excluded.
- [ ] The changed paths and relevant checks were verified.
