export function snapshotFromResult(result, mode) {
  if (result.isError) throw new Error("Android status probe failed. Check the local ADB connection.");
  let data = result.structuredContent;
  if (!data) {
    const text = result.content?.find(item => item.type === "text")?.text;
    if (text) data = JSON.parse(text);
  }
  if (!data?.adb || !Array.isArray(mode === "emulator" ? data.emulators : data.devices)) throw new Error("Incomplete Android status snapshot.");
  return data;
}
export function filterItems(items, query) {
  const value = query.trim().toLowerCase();
  return items.filter(item => [item.name, item.serial, item.model, item.lock?.task, item.lock?.host, item.lock?.project].filter(Boolean).join(" ").toLowerCase().includes(value));
}
export function summaries(items, mode) {
  if (mode === "emulator") return [["Configured AVDs", new Set(items.filter(x => x.configured).map(x => x.name)).size], ["Online", items.filter(x => x.state === "online").length], ["Booting", items.filter(x => x.state === "booting").length], ["Other states", items.filter(x => !["online", "booting"].includes(x.state)).length]];
  return [["Devices", items.length], ["Free", items.filter(x => x.lock.state === "free").length], ["Held", items.filter(x => x.lock.state === "held").length], ["Expired / unknown", items.filter(x => !["free", "held"].includes(x.lock.state)).length]];
}
export function leaseRemaining(lock, elapsed) {
  if (lock.state === "expired") return "Expired · directory still present";
  if (lock.state !== "held") return "—";
  const seconds = Math.max(0, Math.ceil(lock.remainingSeconds - elapsed));
  if (!seconds) return "Elapsed · refresh to verify";
  return seconds >= 3600 ? `${Math.floor(seconds / 3600)}h ${Math.floor(seconds % 3600 / 60)}m remaining` : `${Math.floor(seconds / 60)}m ${seconds % 60}s remaining`;
}
