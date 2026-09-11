# Testing and Verification

- Tie verification to the actual changed surface and add focused coverage when behavior changes.
- When end-to-end coverage is needed and the target environment is available, prefer manually exercising the complete critical flow first and confirm it is repeatable before encoding it as a test.
- If manual end-to-end validation is unavailable, write the most meaningful automated coverage supported by the project and report the missing manual verification.
- Run corresponding tests after code changes, starting with the narrowest meaningful project-supported command.
- When Gradle, Makefile, CMakeLists.txt, package scripts, or other build definitions change, run the corresponding build or compilation.
- Run relevant formatters, lint, type checks, static analysis, and build checks configured by the project.
- Report every relevant check that could not run and why.
- Do not run unrelated expensive suites when narrower checks provide useful coverage.
