# Android status panel sources

This directory owns the shared MCP Apps UI and ADB read helpers for the emulator and device-lock plugins. Each plugin remains independently installable: `npm run build` writes a self-contained HTML resource and a copy of `android_probe.py` into each owning plugin. Edit shared sources here and regenerate; do not edit generated files directly. Each plugin owns its collector and stdio MCP server.

From the repository root:

```bash
npm ci --prefix scripts/android-status
npm run build --prefix scripts/android-status
npm test --prefix scripts/android-status
uv run --script tests/android-status/test-status.py
uv run --with playwright==1.62.0 playwright install chromium
uv run --script tests/android-status/test-panels.py
bash plugins/android-emulator-profile/tests/test-start-avd-docker.sh
bash scripts/build-codex-plugin-package.sh --all
python3 scripts/validate-generated-codex-skills.py ../me.codex
```

Browser tests use a simulated MCP Apps host and fake device snapshots; collector/protocol tests use a fake ADB command and never start an emulator or modify a real lock. An existing Chromium can be selected with `PLAYWRIGHT_CHROMIUM_EXECUTABLE`. `ANDROID_PANEL_SCREENSHOTS` optionally writes preview images from the fake snapshots into an existing directory.

Tests cover initial-result rendering, refresh, stale snapshots, unknown versus free/stopped state, safe text rendering, lease countdowns, explicit serial-scoped screenshots, metadata redaction, and responsive/dark layouts. Runtime hosts must support MCP Apps and the `openai/ui` thread entrypoint. No settings extension is provided.
