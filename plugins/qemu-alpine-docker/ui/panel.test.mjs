import { test } from "node:test";
import assert from "node:assert/strict";
import { snapshotFromResult, filterContainers, containerSummary } from "./view.mjs";
test("tool errors and partial snapshots are rejected", () => {
  assert.throws(() => snapshotFromResult({ isError: true }));
  assert.throws(() => snapshotFromResult({ structuredContent: { vm: {} } }));
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
