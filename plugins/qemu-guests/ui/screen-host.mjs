// Own selection, polling and stale-result rejection independently of rendering.
export class ScreenHost {
  constructor({load, coordinate, schedule, cancel, visible, now}) {
    Object.assign(this, {load, coordinate, schedule, cancel, visible, now});
    this.state = Object.freeze({guestId: null, frame: null, loading: false, error: null, observedAt: null});
    this.listeners = new Set(); this.generation = 0; this.closed = false;
  }
  subscribe(listener) { this.listeners.add(listener); listener(this.state); return () => this.listeners.delete(listener); }
  publish(update) { this.state = Object.freeze({...this.state, ...update}); for (const listener of this.listeners) listener(this.state); }
  async select(guestId) {
    let changed = false;
    await this.coordinate(() => {
      if (this.closed || guestId === this.state.guestId) return;
      ++this.generation; changed = true;
      if (this.timer != null) this.cancel(this.timer);
      this.timer = null;
      this.publish({guestId, frame: null, loading: false, error: null, observedAt: null});
      if (guestId) this.timer = this.schedule(() => { if (this.visible()) void this.refresh(); }, 2000);
    });
    if (changed && guestId) await this.refresh();
  }
  async refresh() {
    let generation, guestId;
    await this.coordinate(() => {
      if (this.closed || !this.state.guestId || this.state.loading) return;
      generation = this.generation; guestId = this.state.guestId;
      this.publish({loading: true});
    });
    if (guestId == null) return;
    try {
      const result = await this.load(guestId);
      if (result.isError) throw new Error("Screen unavailable. The VM may be starting or stopped.");
      const frame = result.structuredContent;
      if (frame?.guestId !== guestId || frame.mimeType !== "image/png" || typeof frame.data !== "string" || frame.data.length > 12 * 1024 * 1024) {
        throw new Error("Invalid screen response.");
      }
      await this.coordinate(() => {
        if (!this.closed && generation === this.generation) this.publish({frame: `data:image/png;base64,${frame.data}`, observedAt: this.now(), error: null});
      });
    } catch (error) {
      await this.coordinate(() => { if (!this.closed && generation === this.generation) this.publish({error: error.message}); });
    } finally {
      await this.coordinate(() => { if (!this.closed && generation === this.generation) this.publish({loading: false}); });
    }
  }
  close() { return this.coordinate(() => {
    this.closed = true; ++this.generation;
    if (this.timer != null) this.cancel(this.timer);
    this.listeners.clear();
  }); }
}
