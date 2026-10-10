# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright==1.62.0"]
# ///
"""Browser checks against a minimal MCP Apps host, without a real VM."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = {
    "observedAt": "2026-10-01T12:00:00Z",
    "vm": {"name": "alpine-dev", "state": "running", "pid": 1234, "diskPresent": True, "provisioned": True, "memoryMiB": "4096", "cpus": "4", "acceleratorPolicy": "auto", "accelerator": "kvm"},
    "services": {"ssh": {"state": "healthy", "port": 2222, "detail": "SSH banner received; authentication was not tested"}, "docker": {"state": "healthy", "port": 2375, "version": "28.0.0", "detail": "Docker API ping succeeded"}},
    "containers": {"state": "available", "items": [
        {"name": "api", "id": "abc123", "image": "alpine:latest", "state": "running", "status": "Up 2 minutes (healthy)", "ports": ["127.0.0.1:20000 → 80/tcp"]},
        {"name": "<img src=x onerror=window.injected=true>", "id": "def456", "image": "redis:7", "state": "exited", "status": "Exited (0)", "ports": []}]},
    "warnings": [],
    "resources": {scope: {"state": "available", "cpuPercent": 12.5, "memoryBytes": 536870912,
                            "memoryLimitBytes": 1073741824, "memoryPercent": 50}
                  for scope in ("host", "qemu", "guest")},
}
SNAPSHOT["containers"]["items"][0]["resources"] = {"state": "available", "cpuPercent": 150,
    "memoryBytes": 67108864, "memoryLimitBytes": 268435456, "memoryPercent": 25}
SNAPSHOT["containers"]["items"][1]["resources"] = {"state": "not-running", "detail": "Container is not running"}
HOST = '''<!doctype html><iframe id="panel" src="/panel" style="width:100%;height:800px;border:0"></iframe><script>
window.snapshot = SNAPSHOT;
window.toolCalls = 0;
window.failRefresh = false;
const send = data => document.getElementById('panel').contentWindow.postMessage({jsonrpc:'2.0',...data}, '*');
window.sendSnapshot = () => send({method:'ui/notifications/tool-result', params:{content:[],structuredContent:window.snapshot}});
window.addEventListener('message', ({data}) => {
  if (data.method === 'ui/initialize') send({id:data.id,result:{protocolVersion:data.params.protocolVersion,hostInfo:{name:'Panel test host',version:'1.0.0'},hostCapabilities:{serverTools:{}},hostContext:{theme:'light',displayMode:'inline'}}});
  else if (data.method === 'ui/notifications/initialized') window.sendSnapshot();
  else if (data.method === 'tools/call') {window.toolCalls++; send({id:data.id,result:window.failRefresh ? {isError:true,content:[{type:'text',text:'Probe failed'}]} : {content:[],structuredContent:window.snapshot}});}
});
</script>'''.replace('SNAPSHOT', json.dumps(SNAPSHOT))

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = (ROOT / "templates/status-panel.html").read_bytes() if self.path == "/panel" else HOST.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(data)
    def log_message(self, *args): pass

server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    with sync_playwright() as playwright:
        executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        browser = playwright.chromium.launch(headless=True, **({"executable_path": executable} if executable else {}))
        page = browser.new_page(viewport={"width": 1150, "height": 860})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"http://127.0.0.1:{server.server_port}/")
        panel = page.frame_locator("#panel")
        panel.locator("#vm-name").get_by_text("alpine-dev", exact=True).wait_for()
        assert "kvm acceleration" in panel.locator("#vm-detail").inner_text()
        assert panel.locator("#host-cpu").inner_text() == "12.5%"
        assert panel.locator("#guest-memory").inner_text() == "512.0 MiB / 1024.0 MiB"
        assert "150.0%" in panel.locator("#containers tr").first.inner_text()
        assert "Container is not running" in panel.locator("#containers tr").nth(1).inner_text()
        assert page.evaluate("window.toolCalls") == 0, "Initial result must not trigger a duplicate probe"
        assert panel.locator("#containers tr").count() == 2
        assert panel.locator("#host-cpu").inner_text() == "12.5%", "Refresh failure retains resource samples"
        page.evaluate("window.snapshot.resources.guest = {state:'unavailable',detail:'Guest resource sample unavailable'}; window.sendSnapshot()")
        panel.locator("#guest-resource-detail").get_by_text("Guest resource sample unavailable", exact=True).wait_for()
        assert panel.locator("#guest-cpu").inner_text() == "—"
        assert panel.locator("#containers img").count() == 0, "Container names must render as text"
        panel.locator("#filter").fill("ALPINE")
        assert panel.locator("#containers tr").count() == 1
        panel.locator("#filter").fill("")
        panel.locator("#refresh").click()
        page.wait_for_function("window.toolCalls === 1")
        page.evaluate("window.failRefresh = true")
        panel.locator("#refresh").click()
        panel.locator("#error").wait_for(state="visible")
        assert "last successful snapshot" in panel.locator("#error").inner_text()
        assert panel.locator("#containers tr").count() == 2
        page.evaluate("window.snapshot.containers = {state:'unavailable',items:[],detail:'Docker API returned HTTP 503'}; window.sendSnapshot()")
        panel.locator("#empty").get_by_text("Docker API returned HTTP 503", exact=True).wait_for()
        page.evaluate("window.snapshot.containers = {state:'available',items:[]}; window.sendSnapshot()")
        panel.locator("#empty").get_by_text("No containers yet.", exact=True).wait_for()
        page.evaluate("window.snapshot.containers = " + json.dumps(SNAPSHOT["containers"]) + "; window.failRefresh = false; window.sendSnapshot()")
        page.clock.install()
        calls = page.evaluate("window.toolCalls")
        panel.locator("#auto").check()
        page.clock.fast_forward(11000)
        page.wait_for_function(f"window.toolCalls === {calls + 1}")
        panel.locator("#auto").uncheck()
        page.clock.fast_forward(11000)
        assert page.evaluate("window.toolCalls") == calls + 1
        page.evaluate("window.snapshot.containers.items[1].name = 'cache'; window.snapshot.resources = " + json.dumps(SNAPSHOT["resources"]) + "; window.sendSnapshot()")
        panel.locator("#containers").get_by_text("cache").wait_for()
        screenshot = os.environ.get("QEMU_PANEL_SCREENSHOT")
        if screenshot: page.screenshot(path=screenshot)
        page.set_viewport_size({"width": 390, "height": 844})
        assert panel.locator("main").evaluate("node => node.scrollWidth <= node.clientWidth"), "Mobile view must fit its viewport"
        page.evaluate("document.getElementById('panel').contentWindow.postMessage({jsonrpc:'2.0',method:'ui/notifications/host-context-changed',params:{theme:'dark'}}, '*')")
        page.wait_for_timeout(100)
        assert panel.locator("html").get_attribute("data-theme") == "dark"
        assert not errors, errors
        browser.close()
        print("PASS: initial snapshot, refresh, errors, filtering, escaping, empty/unavailable states, mobile layout, and theme")
finally:
    server.shutdown()
    server.server_close()
    thread.join()
