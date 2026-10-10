export function snapshotFromResult(result) {
  if (result.isError) throw new Error("Status probe failed. Check the local MCP server and profile.");
  let data = result.structuredContent;
  if (!data) {
    const text = result.content?.find(item => item.type === "text")?.text;
    if (text) data = JSON.parse(text);
  }
  if (!data?.vm || !data.services?.ssh || !data.services?.docker || !Array.isArray(data.containers?.items)) {
    throw new Error("The server returned an incomplete status snapshot.");
  }
  return data;
}

export function filterContainers(items, query) {
  const value = query.trim().toLowerCase();
  return items.filter(item => `${item.name} ${item.image}`.toLowerCase().includes(value));
}

export function containerSummary(containers) {
  if (containers.state !== "available") return "Container list unavailable";
  const running = containers.items.filter(item => item.state === "running").length;
  return `${running} running · ${containers.items.length - running} stopped or inactive`;
}

export function resourceText(value) {
  if (value?.state !== "available") return {cpu: "—", memory: "—", detail: value?.detail || "Resources unavailable"};
  const percent = n => Number.isFinite(n) && n >= 0 ? `${n.toFixed(1)}%` : "—";
  const bytes = n => Number.isFinite(n) && n >= 0 ? `${(n / 1048576).toFixed(1)} MiB` : "—";
  return {cpu: percent(value.cpuPercent), memory: `${bytes(value.memoryBytes)} / ${bytes(value.memoryLimitBytes)}`,
    detail: `Memory ${percent(value.memoryPercent)}${value.cpuPercent == null ? " · CPU awaiting a valid sample" : ""}`};
}
