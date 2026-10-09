import { snapshotFromResult, filterContainers } from "./view.mjs";

// Framework-independent state and asynchronous coordination. IO runs in the MCP server.
export class StatusHost {
  constructor({load, coordinate, now, schedule, cancel}) {
    Object.assign(this, {load, coordinate, now, schedule, cancel});
    this.state = Object.freeze({snapshot: null, items: [], loading: false, error: null, connected: false});
    this.listeners = new Set();
    this.query = ""; this.closed = false; this.generation = 0; this.lastRefresh = 0;
  }
  subscribe(listener) { this.listeners.add(listener); listener(this.state); return () => this.listeners.delete(listener); }
  publish(update) {
    this.state = Object.freeze({...this.state, ...update});
    for (const listener of this.listeners) listener(this.state);
  }
  accept(result) { return this.coordinate(() => {
    if (this.closed) return;
    try {
      const snapshot = structuredClone(snapshotFromResult(result));
      const freeze = value => { if (value && typeof value === "object") { Object.values(value).forEach(freeze); Object.freeze(value); } return value; };
      freeze(snapshot);
      this.publish({snapshot, items: Object.freeze(filterContainers(snapshot.containers.items, this.query)), error: null});
    } catch (error) { this.publish({error: error.message}); }
  }); }
  connect() { return this.coordinate(() => { if (!this.closed) this.publish({connected: true}); }); }
  fail(error) { return this.coordinate(() => { if (!this.closed) this.publish({error: error.message || "Unable to refresh status."}); }); }
  filter(query) { return this.coordinate(() => {
    if (this.closed) return;
    this.query = query;
    this.publish({items: Object.freeze(this.state.snapshot ? filterContainers(this.state.snapshot.containers.items, query) : [])});
  }); }
  async refresh() {
    let generation;
    await this.coordinate(() => {
      if (this.closed || !this.state.connected || this.state.loading) return;
      generation = ++this.generation;
      this.publish({loading: true});
    });
    if (generation == null) return;
    try {
      const result = await this.load();
      if (!this.closed && generation === this.generation) await this.accept(result);
    } catch (error) { if (!this.closed && generation === this.generation) await this.fail(error); }
    finally { await this.coordinate(() => { if (!this.closed && generation === this.generation) {
      this.lastRefresh = this.now(); this.publish({loading: false});
    } }); }
  }
  auto(enabled, visible) { return this.coordinate(() => {
    if (this.closed) return;
    if (this.timer != null) this.cancel(this.timer);
    this.timer = null; this.lastRefresh = this.now();
    if (enabled) this.timer = this.schedule(() => {
      if (visible() && this.now() - this.lastRefresh >= 10000) void this.refresh();
    }, 1000);
  }); }
  close() { return this.coordinate(() => {
    this.closed = true; ++this.generation;
    if (this.timer != null) this.cancel(this.timer);
    this.listeners.clear();
  }); }
}
