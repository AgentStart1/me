import { App, applyDocumentTheme, applyHostStyleVariables } from "@modelcontextprotocol/ext-apps";
import { containerSummary, resourceText } from "./view.mjs";
import { StatusHost } from "./host.mjs";
import { ScreenHost } from "./screen-host.mjs";
const app = new App({ name: "QEMU Docker Status", version: "0.4.0" }, {});
const el = id => document.getElementById(id);
let snapshot;
let coordination = Promise.resolve();
const coordinate = action => { const next = coordination.then(action); coordination = next.catch(() => {}); return next; };
const screen = new ScreenHost({load: guestId => app.callServerTool({name: "qemu_guest_screen", arguments: {guest_id: guestId}}),
  coordinate, schedule: (action, ms) => setInterval(action, ms), cancel: timer => clearInterval(timer),
  visible: () => !document.hidden, now: () => Date.now()});
const host = new StatusHost({load: () => app.callServerTool({name: "qemu_docker_status", arguments: {}}),
  coordinate: action => { const next = coordination.then(action); coordination = next.catch(() => {}); return next; },
  now: () => Date.now(), schedule: (action, ms) => setInterval(action, ms), cancel: timer => clearInterval(timer)});
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
  const items = host.state.items;
  setText("count", `(${containers.items.length})`);
  setText("summary", containerSummary(containers));
  const body = el("containers"); body.replaceChildren();
  for (const item of items) {
    const row = document.createElement("tr");
    const resources = resourceText(item.resources);
    for (const [text, detail, state] of [[item.name, item.id], [item.image], [item.state, item.status, true], [resources.cpu], [resources.memory, resources.detail], [item.ports.join("\n") || "—"]]) {
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
function accept(value) {
  snapshot = value;
  el("error").hidden = true; el("loading").hidden = true; el("dashboard").hidden = false;
  setText("vm-name", snapshot.vm.name);
  el("vm-state").replaceChildren(badge(snapshot.vm.state));
  const vm = snapshot.vm;
  setText("vm-detail", `${vm.pid ? `PID ${vm.pid} · ` : ""}${vm.diskPresent ? "Disk present" : "No disk"} · ${vm.provisioned ? "Provisioned" : "Not verified"} · Profile: ${vm.cpus || "?"} vCPU / ${vm.memoryMiB || "?"} MiB · ${vm.accelerator || "unknown"} acceleration (${vm.acceleratorPolicy} policy)`);
  for (const scope of ["host", "qemu", "guest"]) {
    const value = resourceText(snapshot.resources?.[scope]);
    setText(`${scope}-cpu`, value.cpu);
    setText(`${scope}-memory`, value.memory);
    setText(`${scope}-resource-detail`, value.detail);
  }
  for (const service of ["ssh", "docker"]) {
    const value = snapshot.services[service];
    setText(`${service}-value`, service === "docker" && value.version ? `v${value.version}` : `Port ${value.port}`);
    el(`${service}-state`).replaceChildren(badge(value.state));
    setText(`${service}-detail`, value.detail);
  }
  el("warnings").replaceChildren();
  for (const warning of snapshot.warnings || []) { const node = document.createElement("div"); node.className = "notice"; node.textContent = warning; el("warnings").append(node); }
  renderContainers();
  renderGuests();
  setText("observed", `Last observed ${new Date(snapshot.observedAt).toLocaleTimeString()}`);
}
function renderGuests() {
  const items = snapshot.workGuests?.items || [];
  const list = el("work-guests"); list.replaceChildren();
  setText("work-summary", items.length ? `${items.length} work VMs · shared Alpine Docker backend` : "No work VMs registered yet.");
  for (const guest of items) {
    const card = document.createElement("article"); card.className = "card";
    card.dataset.guestId = guest.id;
    const title = document.createElement("h2"); title.textContent = guest.name; card.append(title, badge(guest.state));
    const detail = document.createElement("p"); detail.className = "detail";
    detail.textContent = `${guest.os} · ${guest.graphical ? "Graphical" : "Headless"} · ${guest.cpus} vCPU / ${guest.memory} MiB · SSH ${guest.ssh_port}${guest.appiumEndpoint ? ` · Appium ${guest.appiumEndpoint} (SSH tunnel)` : ""}`;
    card.append(detail);
    if (guest.graphical) {
      const button = document.createElement("button"); button.textContent = "View screen";
      button.disabled = !guest.screenAvailable;
      button.addEventListener("click", () => { void screen.select(guest.id); }); card.append(button);
    }
    list.append(card);
  }
  if (!items.some(item => item.id === screen.state.guestId && item.screenAvailable)) {
    void screen.select(items.find(item => item.screenAvailable)?.id || null);
  }
}
const unsubscribeScreen = screen.subscribe(state => {
  const image = el("work-screen");
  if (state.frame && image.getAttribute("src") !== state.frame) image.src = state.frame;
  if (!state.frame) image.removeAttribute("src");
  image.hidden = !state.frame;
  const name = snapshot?.workGuests?.items?.find(item => item.id === state.guestId)?.name;
  setText("screen-title", name ? `${name} · Live screen` : "Work VM screen");
  setText("screen-detail", state.error || (state.guestId ? state.observedAt ? `Read-only · Refreshes every 2s · ${new Date(state.observedAt).toLocaleTimeString()}` : "Waiting for a screen frame…" : "Select a running graphical VM to view its screen."));
});
function showError(error) {
  setText("error", `${error.message || "Unable to refresh status."}${snapshot ? " Showing the last successful snapshot." : ""}`);
  el("error").hidden = false; el("loading").hidden = true;
}
function theme(context) {
  if (context.theme) applyDocumentTheme(context.theme);
  if (context.styles?.variables) applyHostStyleVariables(context.styles.variables);
}
const unsubscribe = host.subscribe(state => {
  if (state.snapshot) accept(state.snapshot);
  if (state.error) showError(new Error(state.error));
  el("refresh").disabled = !state.connected || state.loading;
  setText("refresh", state.loading ? "Refreshing…" : "Refresh");
});
app.ontoolresult = result => { void host.accept(result); };
app.ontoolcancelled = () => { void host.fail(new Error("The status probe was cancelled.")); };
app.onhostcontextchanged = theme;
el("refresh").addEventListener("click", () => { void host.refresh(); });
el("filter").addEventListener("input", () => { void host.filter(el("filter").value); });
el("auto").addEventListener("change", () => { void host.auto(el("auto").checked, () => !document.hidden); });
window.addEventListener("pagehide", () => { unsubscribe(); unsubscribeScreen(); void host.close(); void screen.close(); }, {once: true});
try {
  await app.connect(); await host.connect();
  theme(app.getHostContext() || {});
  // Initial results arrive from the host. Do not duplicate the initial probe.
} catch (error) { await host.fail(error); }
