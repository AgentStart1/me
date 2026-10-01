import { App, applyDocumentTheme, applyHostStyleVariables } from "@modelcontextprotocol/ext-apps";
import { snapshotFromResult, filterItems, summaries, leaseRemaining } from "./view.mjs";
const mode = PANEL_MODE;
const title = mode === "emulator" ? "Android Emulators" : "Device Leases";
const tool = mode === "emulator" ? "android_emulator_status" : "android_device_lock_status";
const app = new App({name:title, version:"0.4.0"}, {});
const el = id => document.getElementById(id);
const text = (id, value) => { el(id).textContent = value; };
let snapshot, receivedAt = 0, connected = false, busy = false, lastRefresh = 0, captureBusy = false, captureId = 0;
let countdowns = [];
text("subtitle", mode === "emulator" ? "AVD inventory, boot readiness & screen previews" : "Shared Android devices · Test ownership & lease expiry");
text("footnote", mode === "emulator" ? "Read-only · Screens captured only on request" : "Read-only · Observation does not acquire or release a lock");
function badge(state) {
  const node = document.createElement("span"); node.className = "badge";
  if (["online", "free", "held", "booting", "expired", "offline", "unauthorized", "unknown", "unavailable"].includes(state)) node.classList.add(state);
  node.textContent = state; return node;
}
function cell(value, detail, state=false) {
  const node = document.createElement("td");
  if (state) node.append(badge(value)); else node.textContent = value || "—";
  if (detail) {const small = document.createElement("small"); small.textContent = detail; node.append(small);}
  return node;
}
function tickLeases() {
  for (const [node, lock] of countdowns) node.textContent = leaseRemaining(lock, (performance.now() - receivedAt) / 1000);
}
function render() {
  const all = mode === "emulator" ? snapshot.emulators : snapshot.devices;
  const items = filterItems(all, el("filter").value);
  el("metrics").replaceChildren();
  for (const [name, count] of summaries(all, mode)) {const metric = document.createElement("div"); metric.className = "metric"; const value = document.createElement("strong"); value.textContent = count; const label = document.createElement("span"); label.textContent = name; metric.append(value,label); el("metrics").append(metric);}
  text("list-title", mode === "emulator" ? "Emulators" : "Device leases");
  text("list-detail", mode === "emulator" ? "Configured AVDs and connected emulators" : snapshot.lockPath);
  const headings = mode === "emulator" ? ["Emulator", "State", "Android", "Configuration", "Preview"] : ["Device", "Lease", "Task / project", "Owner", "Expiry"];
  const headingRow = document.createElement("tr");
  for (const heading of headings) {const th = document.createElement("th"); th.scope = "col"; th.textContent = heading; headingRow.append(th);}
  el("columns").replaceChildren(headingRow); el("rows").replaceChildren(); countdowns = [];
  for (const item of items) {
    const row = document.createElement("tr");
    if (mode === "emulator") {
      row.append(cell(item.name, item.serial || "Not connected"),cell(item.state,item.detail,true),cell(item.androidVersion ? `Android ${item.androidVersion}` : item.api ? `API ${item.api}` : "Unknown", item.androidVersion && item.api ? `API ${item.api}` : ""),cell([item.abi,item.memory ? `${item.memory}${/^\d+$/.test(item.memory) ? " MB" : ""} RAM (config)` : "",item.resolution].filter(Boolean).join(" · ") || (item.configured ? "Local AVD" : "Remote or unmapped AVD")));
      const action = document.createElement("td");
      if (item.serial && item.state === "online") {const button = document.createElement("button"); button.className = "capture"; button.textContent = "Capture screen"; button.disabled = captureBusy; button.setAttribute("aria-label", `Capture screen of ${item.name}`); button.addEventListener("click",()=>capture(item)); action.append(button);} else action.textContent = "—";
      row.append(action);
    } else {
      const lock = item.lock;
      row.append(cell(item.model || item.serial,item.model ? item.serial : item.connection),cell(lock.state,lock.detail,true),cell(lock.task,lock.project),cell(lock.host,lock.pid ? `PID ${lock.pid}` : ""));
      const expiry = cell(""); countdowns.push([expiry,lock]); row.append(expiry);
    }
    el("rows").append(row);
  }
  tickLeases();
  el("table").hidden = !items.length; el("empty").hidden = Boolean(items.length);
  text("empty", snapshot.adb.state !== "available" ? snapshot.adb.detail : all.length ? "No matching entries." : mode === "emulator" ? "No configured AVDs or connected emulators." : "No connected Android devices.");
  el("clock-note").hidden = mode !== "locks"; text("clock-note", snapshot.clockNote || "");
}
function accept(result) {
  snapshot = snapshotFromResult(result,mode); receivedAt = performance.now();
  el("error").hidden = true; el("loading").hidden = true; el("dashboard").hidden = false;
  el("warnings").replaceChildren();
  const warnings = [...(snapshot.warnings || [])];
  if (snapshot.adb.state !== "available") warnings.unshift(snapshot.adb.detail);
  for (const warning of warnings) {const node=document.createElement("div"); node.className="notice"; node.textContent=warning; el("warnings").append(node);}
  render(); text("observed",`Last observed ${new Date(snapshot.observedAt).toLocaleTimeString()}`);
}
function fail(error) {text("error",`${error.message || "Probe failed."}${snapshot ? " Showing the last successful snapshot." : ""}`); el("error").hidden=false;el("loading").hidden=true;}
async function refresh() {
  if (!connected || busy) return;
  busy=true; el("refresh").disabled=true;text("refresh","Refreshing…");
  try {accept(await app.callServerTool({name:tool,arguments:{}}));} catch(error) {fail(error);}
  finally {busy=false;lastRefresh=Date.now();el("refresh").disabled=false;text("refresh","Refresh");}
}
async function capture(item) {
  if (captureBusy || !connected) return;
  captureBusy=true;const current=++captureId;render();el("screen").hidden=false;el("screenshot").hidden=true;el("screenshot").removeAttribute("src");
  text("screen-title",`${item.name} · Screen preview`);text("screen-detail",item.serial);text("screen-message","Capturing screen…");
  try {
    const result=await app.callServerTool({name:"android_emulator_screenshot",arguments:{serial:item.serial}});
    if(current!==captureId) return;
    if(result.isError) throw new Error("Screen capture failed. Refresh the emulator status and try again.");
    const image=result.content?.find(content=>content.type==="image" && content.mimeType==="image/png");
    if(!image) throw new Error("No PNG screenshot returned.");
    if(!snapshot.emulators.some(device=>device.serial===item.serial && device.state==="online")) throw new Error("The selected emulator is no longer online.");
    el("screenshot").src=`data:image/png;base64,${image.data}`;el("screenshot").alt=`Screen of ${item.name}`;el("screenshot").hidden=false;text("screen-message","Snapshot captured on request; not a live stream.");
  } catch(error) {if(current===captureId) text("screen-message",error.message);}
  finally {captureBusy=false;if(snapshot) render();}
}
function theme(context) {if(context.theme) applyDocumentTheme(context.theme);if(context.styles?.variables) applyHostStyleVariables(context.styles.variables);}
app.ontoolresult=result=>{try{accept(result);}catch(error){fail(error);}};
app.ontoolcancelled=()=>fail(new Error("The status probe was cancelled."));
app.onhostcontextchanged=theme;
el("refresh").addEventListener("click",refresh);el("filter").addEventListener("input",()=>{if(snapshot) render();});
el("auto").addEventListener("change",()=>{lastRefresh=Date.now();});
el("close-screen").addEventListener("click",()=>{captureId++;el("screen").hidden=true;el("screenshot").removeAttribute("src");});
setInterval(()=>{tickLeases();if(el("auto").checked&&!document.hidden&&Date.now()-lastRefresh>=10000) refresh();},1000);
try {await app.connect();connected=true;el("refresh").disabled=false;theme(app.getHostContext()||{});}catch(error){fail(error);}
