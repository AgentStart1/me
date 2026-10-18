# Testing and Verification

## Test contracts and overloaded tests

Apply these checks to unit, integration, Compose and other UI, and end-to-end tests when adding, modifying, refactoring, or reviewing them. For ordinary changes, inspect new and affected tests; audit the whole repository only when requested.

- Center each test on one clear, nameable primary behavior contract. Multiple assertions may be needed to verify that contract.
- Match the name to the actual action and assertions. Verify every outcome promised by the name: clicking an action or finding a common control does not establish that the business operation succeeded.
- Separate fixture setup, the primary action, and outcome verification. Multiple production API calls used to prepare shared data do not by themselves overload a test.
- Look for independent production APIs, unrelated business operations or state transitions chained in one case, a fresh fixture/reset/clear starting another scenario, or helpers concealing multiple responsibilities. An earlier behavior's failure should not prevent an independent contract from being exercised and reported.
- Inspect parameter and platform branches: an unexecuted branch is not covered. Parameterization should express an input matrix for the same contract, including the same storage contract across backends.
- Judge behavioral independence, not line count, click count, assertion count, or the number of production calls.

Split independent behaviors into cases that can run and report failures separately, sharing necessary fixture setup. Preserve the original business assertions when splitting; do not simplify by deleting coverage or hiding independent scenarios inside a helper.

Keep multiple assertions for related consequences of one event or fields of one object. Keep flows whose dependency is necessary to establish the contract, such as write/read persistence, recovery after failure, or resource release after cancellation. A continuous E2E user journey may remain together when its steps have real dependencies and its overall contract is stated; do not chain unrelated business operations into one smoke test.

In review findings, identify the concrete test, its independent contracts, and a proposed split. Distinguish confirmed contract or overload problems from optional cleanup and dependent flows that should remain together.

### Examples

| Scenario | Expected judgment |
| --- | --- |
| Call independent `runAlphaJob()` and `runBetaJob()`, then assert each job's records. | Split by job contract; retain shared data preparation in the fixture and both sets of business assertions. |
| Call `save()`, create a new instance, then `load()` and assert the same value. | Keep together: the calls establish one persistence contract. |
| Check several inputs to the same filter function. | Keep an input matrix or parameterize the same filtering contract; do not require one assertion per test. |
| Verify that a refresh failure leaves another data source intact, then click an item to verify navigation. | Split navigation into its own case with an independent fixture; preserve the refresh-isolation assertions. |
| Cancel an operation, then verify task completion, handle closure, and preservation of the cancellation exception. | Keep together: these are consequences of one cancellation-cleanup contract. |

## Execution and reporting

- Tie verification to the actual changed surface and add focused coverage when behavior changes.
- When end-to-end coverage is needed and the target environment is available, prefer manually exercising the complete critical flow first and confirm it is repeatable before encoding it as a test.
- If manual end-to-end validation is unavailable, write the most meaningful automated coverage supported by the project and report the missing manual verification.
- Run corresponding tests after code changes, starting with the narrowest meaningful project-supported command.
- When Gradle, Makefile, CMakeLists.txt, package scripts, or other build definitions change, run the corresponding build or compilation.
- Run relevant formatters, lint, type checks, static analysis, and build checks configured by the project.
- Report every relevant check that could not run and why.
- Do not run unrelated expensive suites when narrower checks provide useful coverage.
