import { App, applyDocumentTheme, applyHostStyleVariables } from "@modelcontextprotocol/ext-apps";
import { snapshotFromResult, filterContainers, containerSummary } from "./view.mjs";
const app = new App({ name: "QEMU Docker Status", version: "0.4.0" }, {});
const el = id => document.getElementById(id);
let snapshot, connected = false, busy = false, lastRefresh = 0;
const setText = (id, text) => { el(id).textContent = text; };
function badge(state) {
  const node = document.createElement("span");
  node.classList.add("badge");
  if (["healthy", "running", "unreachable", "stopped", "unknown", "unavailable", "unhealthy"].includes(state)) node.classList.add(state);
  node.textContent = state;
  return node;
}
function renderContainers() {
  const containers = snapshot.containers;
  const items = filterContainers(containers.items, el("filter").value);
  setText("count", `(${containers.items.length})`);
  setText("summary", containerSummary(containers));
  const body = el("containers"); body.replaceChildren();
  for (const item of items) {
    const row = document.createElement("tr");
    for (const [text, detail, state] of [[item.name, item.id], [item.image], [item.state, item.status, true], [item.ports.join("\n") || "—"]]) {
      const cell = document.createElement("td");
      if (state) cell.append(badge(text)); else cell.textContent = text;
      if (detail) { const small = document.createElement("small"); small.textContent = detail; cell.append(small); }
      row.append(cell);
    }
    body.append(row);
  }
  el("table").hidden = !items.length;
  el("empty").hidden = Boolean(items.length);
  setText("empty", containers.state !== "available" ? containers.detail || "Docker could not return its container list." : containers.items.length ? "No matching containers." : "No containers yet.");
}
function accept(result) {
  snapshot = snapshotFromResult(result);
  el("error").hidden = true; el("loading").hidden = true; el("dashboard").hidden = false;
  setText("vm-name", snapshot.vm.name);
  el("vm-state").replaceChildren(badge(snapshot.vm.state));
  const vm = snapshot.vm;
  setText("vm-detail", `${vm.pid ? `PID ${vm.pid} · ` : ""}${vm.diskPresent ? "Disk present" : "No disk"} · ${vm.provisioned ? "Provisioned" : "Not verified"} · Profile: ${vm.cpus || "?"} vCPU / ${vm.memoryMiB || "?"} MiB · ${vm.accelerator || "unknown"} acceleration (${vm.acceleratorPolicy} policy)`);
  for (const service of ["ssh", "docker"]) {
    const value = snapshot.services[service];
    setText(`${service}-value`, service === "docker" && value.version ? `v${value.version}` : `Port ${value.port}`);
    el(`${service}-state`).replaceChildren(badge(value.state));
    setText(`${service}-detail`, value.detail);
  }
  el("warnings").replaceChildren();
  for (const warning of snapshot.warnings || []) { const node = document.createElement("div"); node.className = "notice"; node.textContent = warning; el("warnings").append(node); }
  renderContainers();
  setText("observed", `Last observed ${new Date(snapshot.observedAt).toLocaleTimeString()}`);
}
function showError(error) {
  setText("error", `${error.message || "Unable to refresh status."}${snapshot ? " Showing the last successful snapshot." : ""}`);
  el("error").hidden = false; el("loading").hidden = true;
}
async function refresh() {
  if (!connected || busy) return;
  busy = true; el("refresh").disabled = true; setText("refresh", "Refreshing…");
  try { accept(await app.callServerTool({ name: "qemu_docker_status", arguments: {} })); }
  catch (error) { showError(error); }
  finally { busy = false; lastRefresh = Date.now(); el("refresh").disabled = false; setText("refresh", "Refresh"); }
}
function theme(context) {
  if (context.theme) applyDocumentTheme(context.theme);
  if (context.styles?.variables) applyHostStyleVariables(context.styles.variables);
}
app.ontoolresult = result => { try { accept(result); } catch (error) { showError(error); } };
app.ontoolcancelled = () => showError(new Error("The status probe was cancelled."));
app.onhostcontextchanged = theme;
el("refresh").addEventListener("click", refresh);
el("filter").addEventListener("input", () => { if (snapshot) renderContainers(); });
el("auto").addEventListener("change", () => { lastRefresh = Date.now(); });
setInterval(() => { if (el("auto").checked && !document.hidden && Date.now() - lastRefresh >= 10000) refresh(); }, 1000);
try {
  await app.connect(); connected = true; el("refresh").disabled = false;
  theme(app.getHostContext() || {});
  // Initial results arrive from the host. Do not duplicate the initial probe.
} catch (error) { showError(error); }
