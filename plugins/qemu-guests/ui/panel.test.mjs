import { test } from "node:test";
import assert from "node:assert/strict";
import { snapshotFromResult, filterContainers, containerSummary } from "./view.mjs";
import { resourceText } from "./view.mjs";
import { StatusHost } from "./host.mjs";
test("tool errors and partial snapshots are rejected", () => {
  assert.throws(() => snapshotFromResult({ isError: true }));
  assert.throws(() => snapshotFromResult({ structuredContent: { vm: {} } }));
});
test("resource labels distinguish zero, unavailable, and missing CPU baselines", () => {
  assert.equal(resourceText({state: "available", cpuPercent: 0, memoryBytes: 1048576, memoryLimitBytes: 2097152, memoryPercent: 50}).cpu, "0.0%");
  assert.equal(resourceText({state: "not-running", detail: "Container is not running"}).detail, "Container is not running");
  assert.equal(resourceText({state: "available", cpuPercent: null}).cpu, "—");
  assert.match(resourceText({state: "available", cpuPercent: null}).detail, /awaiting/);
});
test("Host serializes refreshes, retains stale data, filters and discards loads after close", async () => {
  let queue = Promise.resolve(), complete, calls = 0, cancelled = false;
  const host = new StatusHost({load: () => { calls++; return new Promise(resolve => {complete = resolve;}); },
    coordinate: action => { const next = queue.then(action); queue = next; return next; },
    now: () => 10000, schedule: () => 1, cancel: () => {cancelled = true;}});
  const snapshot = {vm: {}, services: {ssh: {}, docker: {}}, containers: {state: "available", items: [{name: "api", image: "alpine"}]}};
  await host.connect(); await host.accept({structuredContent: snapshot});
  assert.ok(Object.isFrozen(host.state.snapshot.containers.items[0]));
  const refresh = host.refresh(); await queue; await host.refresh(); assert.equal(calls, 1);
  complete({isError: true}); await refresh;
  assert.equal(host.state.snapshot.containers.items.length, 1); assert.match(host.state.error, /failed/);
  await host.filter("redis"); assert.equal(host.state.items.length, 0);
  await host.auto(true, () => true);
  const pending = host.refresh(); await queue;
  await host.close(); const state = host.state;
  complete({structuredContent: snapshot}); await pending;
  assert.equal(host.state, state); assert.ok(cancelled);
});
test("empty and unavailable container lists remain distinct", () => {
  assert.equal(containerSummary({ state: "available", items: [] }), "0 running · 0 stopped or inactive");
  assert.equal(containerSummary({ state: "unavailable", items: [] }), "Container list unavailable");
});
test("container filtering preserves states and treats search as literal text", () => {
  const items = [{name: "api", image: "Alpine:latest", state: "running"}, {name: "cache", image: "redis", state: "exited"}];
  assert.deepEqual(filterContainers(items, " ALPINE "), [items[0]]);
  assert.deepEqual(filterContainers(items, "<script>"), []);
  assert.equal(containerSummary({state: "available", items}), "1 running · 1 stopped or inactive");
});
