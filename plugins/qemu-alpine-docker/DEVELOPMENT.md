# QEMU status panel development

The resource collector is separate from test-run metrics. `scripts/status_resources.py`
samples the local system and verified QEMU process through psutil, reads guest counters
using `templates/guest-resource-sample.sh` and the existing SSH key, and derives container
usage from Docker's non-streaming stats endpoint. Every sample has an explicit state;
missing CPU deltas remain null. Container memory subtracts cgroup v1 `total_inactive_file`
or cgroup v2 `inactive_file`, matching Docker's Linux CLI convention. Probe failures
remain scoped to the resource sample and never replace a valid inventory.

`ui/host.mjs` owns immutable snapshots, filtering, refresh coordination and lifecycle
cancellation independently of the DOM. The application injects serial coordination,
tool IO, timer and clock dependencies. Blocking resource IO and CPU sampling run in
the Python MCP server, not the browser event loop. `ui/panel.mjs` adapts Host state to
the view; `ui/view.mjs` formats values. Rebuild `templates/status-panel.html` after UI edits.

From the plugin root:

```bash
npm run build --prefix ui
npm test --prefix ui
uv run --script tests/test-status.py
uv run --script tests/test-status-panel.py
```

The browser suite uses a simulated MCP Apps host and covers resource rendering,
unavailable values, stale snapshots, responsive layout and refresh. Set
`PLAYWRIGHT_CHROMIUM_EXECUTABLE` to an installed Chromium executable if Playwright's
own Chromium is unavailable. It does not establish hardware acceleration or real
guest/cgroup availability; validate those with an already-running VM separately.
