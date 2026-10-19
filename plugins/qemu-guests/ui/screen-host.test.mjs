import {test} from "node:test";
import assert from "node:assert/strict";
import {ScreenHost} from "./screen-host.mjs";

function fixture(load) {
  let queue = Promise.resolve(), timer, cancelled = 0;
  const host = new ScreenHost({load, coordinate: action => { const next = queue.then(action); queue = next; return next; },
    schedule: action => { timer = action; return 1; }, cancel: () => { cancelled++; }, visible: () => true, now: () => 42});
  return {host, flush: () => queue, tick: () => timer(), cancelled: () => cancelled};
}
test("switching guests rejects a late screen from the old guest", async () => {
  const complete = {};
  const {host, flush} = fixture(id => new Promise(resolve => { complete[id] = resolve; }));
  const first = host.select("first"); await flush(); await flush();
  const second = host.select("second"); await flush(); await flush();
  complete.second({structuredContent: {guestId: "second", mimeType: "image/png", data: "second-frame"}});
  await second;
  complete.first({structuredContent: {guestId: "first", mimeType: "image/png", data: "old-frame"}});
  await first;
  assert.equal(host.state.guestId, "second");
  assert.match(host.state.frame, /second-frame$/);
  await host.close();
});
test("closing the screen host cancels polling and discards pending capture", async () => {
  let complete;
  const {host, flush, cancelled} = fixture(() => new Promise(resolve => { complete = resolve; }));
  const pending = host.select("work"); await flush(); await flush();
  await host.close(); const state = host.state;
  complete({structuredContent: {guestId: "work", mimeType: "image/png", data: "late"}});
  await pending;
  assert.equal(host.state, state); assert.equal(cancelled(), 1);
});
test("failed capture retains the last frame and reports a stale-screen error", async () => {
  let failed = false;
  const {host} = fixture(async () => failed ? {isError: true} : {structuredContent: {guestId: "work", mimeType: "image/png", data: "frame"}});
  await host.select("work"); const frame = host.state.frame;
  failed = true; await host.refresh();
  assert.equal(host.state.frame, frame); assert.match(host.state.error, /unavailable/);
  await host.close();
});
