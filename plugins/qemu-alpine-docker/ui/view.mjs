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
