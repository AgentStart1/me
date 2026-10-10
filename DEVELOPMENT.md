# Development

Run `bash scripts/build-claude-plugin-package.sh --all` and `bash scripts/build-codex-plugin-package.sh --all` to generate sibling directories. Inspect existing sibling checkouts first: generated `plugins/`, marketplace directories, and README are replaced; unrelated files are preserved. Do not commit or push generated repositories locally.

Run `python scripts/validate-plugin-packages.py --client claude ../me.claude` and `python scripts/validate-plugin-packages.py --client codex ../me.codex`, plus `bash tests/test-build-plugin-cli.sh` and `python tests/test-plugin-packages.py`. The Python test covers generated content, routing, regeneration, cleanup, and path protection; the shell test covers both client command entries, help, arguments, and dispatch. Validation dependencies are in `scripts/requirements-validation.txt`.

The sync workflow needs `UPSTREAM_GITHUB_TOKEN` with repository write and pull-request permissions for both existing destination repositories. It opens a separate generated PR for each client; destination PRs must merge before users receive updates. Start a new Codex thread after synchronized plugin updates are published and installed.

## Continuous integration

Two validation workflows run on every pull request, pushes to `main`, and
manual dispatch. `validate-client-packages.yml` (Validate client packages)
validates all portable sources and both Codex and Claude distributions.
`test-plugins.yml` (Test plugins) runs plugin runtime suites and checks that
every suite is connected to CI. They use separate concurrency groups.
Together they cover:

- All nine portable plugins and both generated client distributions, including
  prompt-only plugins, skill frontmatter, agent routing, resource integrity,
  regeneration, CLI behavior, and generated Codex skill checks.
- `diff-sharing` and `test-report-sharing` shell suites in separate matrix jobs.
- Android status UI, backend, browser checks, and emulator startup regressions.
- QEMU status UI, backend, browser checks, and VM shell regression suites.
- Docker proxy Go tests with the race detector.
- The unprivileged QEMU container runtime smoke test.

Python, npm, uv, Go, Playwright Chromium, and Docker build layers use Actions
caches. Browser system dependencies are installed on every fresh runner even
when Chromium is cached. Package checks run once, independently of runtime
jobs. New executable plugins must add their runtime suites to `test-plugins.yml`;
all plugin manifests and portable prompts are automatically included in package
validation. Prompt checks verify packaging and structure, not model behavior.

Run `python tests/test-validation-workflow.py` to check runtime suite coverage
when changing CI.

Run shell suites with `bash plugins/<plugin>/tests/test-*.sh` one file at a time,
UI suites with `npm ci`, `npm run build`, and `npm test` in their UI directory,
and browser/backend suites with `uv run --script <test.py>`. Run proxy tests
with `go test -race ./...` in `plugins/qemu-alpine-docker/scripts/docker-proxy`.
The container job requires Docker and a Linux runtime; see its workflow steps
for the build and execution commands.
