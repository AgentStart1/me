# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright==1.62.0"]
# ///
"""Exercise both UI bundles against a minimal MCP Apps host with fake devices."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[2]
PNG='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg=='
COMMON={'observedAt':'2026-10-01T12:00:00Z','adb':{'state':'available','detail':'ADB device list received'},'warnings':[]}
SNAPSHOTS={
 'emulator':{**COMMON,'emulators':[
  {'name':'Pixel · API 35','serial':'emulator-5554','state':'online','configured':True,'androidVersion':'15','api':'35','abi':'x86_64','memory':'2048','resolution':'1080 × 2400'},
  {'name':'Tablet · API 35','serial':'emulator-5556','state':'booting','configured':True,'abi':'x86_64','api':'35'},
  {'name':'Wear OS','serial':None,'state':'disconnected','configured':True,'api':'34'}]},
 'locks':{**COMMON,'lockPath':'/data/local/tmp/android-device-test.lock.d','clockNote':"Lease expiry uses this host's clock. No waiting queue is recorded by the lock helper.",'devices':[
  {'serial':'emulator-5554','model':'Pixel','connection':'device','lock':{'state':'held','task':'Login smoke test','project':'mobile-app','host':'ci-runner','pid':1234,'remainingSeconds':30,'expiresAt':4102444800}},
  {'serial':'emulator-5556','model':'Tablet','connection':'device','lock':{'state':'free','detail':'No lock directory at observation time'}},
  {'serial':'phone-01','model':'Test phone','connection':'device','lock':{'state':'expired','task':'Checkout suite','host':'local-runner','pid':4321,'remainingSeconds':0}},
  {'serial':'phone-02','model':'Offline phone','connection':'offline','lock':{'state':'unavailable','detail':'Lock ownership is unknown'}}]}}
PLUGINS={'emulator':'android-emulator-profile','locks':'android-device-lock'}
HOST='''<!doctype html><iframe id="panel" src="/MODE" style="width:100%;height:850px;border:0"></iframe><script>
window.snapshot=SNAPSHOT;window.calls=0;window.captures=0;window.fail=false;
const send=data=>document.getElementById('panel').contentWindow.postMessage({jsonrpc:'2.0',...data},'*');
window.sendSnapshot=()=>send({method:'ui/notifications/tool-result',params:{content:[],structuredContent:window.snapshot}});
window.addEventListener('message',({data})=>{
 if(data.method==='ui/initialize') send({id:data.id,result:{protocolVersion:data.params.protocolVersion,hostInfo:{name:'Panel test host',version:'1.0.0'},hostCapabilities:{serverTools:{}},hostContext:{theme:'light',displayMode:'inline'}}});
 else if(data.method==='ui/notifications/initialized') window.sendSnapshot();
 else if(data.method==='tools/call') {
  if(data.params.name==='android_emulator_screenshot'){window.captures++;window.captureSerial=data.params.arguments.serial;send({id:data.id,result:{content:[{type:'image',mimeType:'image/png',data:'PNG_DATA'}]}});}
  else {window.calls++;send({id:data.id,result:window.fail?{isError:true,content:[]}:{content:[],structuredContent:window.snapshot}});}
 }
});</script>'''
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path.startswith('/host-'):
   mode=self.path.removeprefix('/host-')
   data=HOST.replace('MODE',mode).replace('SNAPSHOT',json.dumps(SNAPSHOTS[mode])).replace('PNG_DATA',PNG).encode()
  elif self.path[1:] in PLUGINS:data=(ROOT/'plugins'/PLUGINS[self.path[1:]]/'templates/status-panel.html').read_bytes()
  else:self.send_error(404);return
  self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(data)
 def log_message(self,*args):pass
server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:
 with sync_playwright() as playwright:
  executable=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE')
  browser=playwright.chromium.launch(headless=True,**({'executable_path':executable} if executable else {}))
  for mode in PLUGINS:
   page=browser.new_page(viewport={'width':1200,'height':900});errors=[]
   page.on('pageerror',lambda error:errors.append(str(error)))
   page.clock.install()
   page.goto(f'http://127.0.0.1:{server.server_port}/host-{mode}')
   panel=page.frame_locator('#panel');panel.locator('#dashboard').wait_for(state='visible')
   assert page.evaluate('window.calls')==0
   assert page.evaluate('window.captures')==0
   rows=3 if mode=='emulator' else 4
   assert panel.locator('#rows tr').count()==rows
   screenshot_dir=os.environ.get('ANDROID_PANEL_SCREENSHOTS')
   page.clock.run_for(200)
   if screenshot_dir:page.screenshot(path=str(Path(screenshot_dir)/f'android-{mode}-panel.png'))
   panel.locator('#filter').fill('5554');assert panel.locator('#rows tr').count()==1
   panel.locator('#filter').fill('');panel.locator('#refresh').click()
   page.wait_for_function('window.calls===1')
   expect(panel.locator('#refresh')).to_be_enabled()
   if mode=='emulator':
    assert panel.locator('.capture').count()==1
    panel.locator('.capture').click();panel.locator('#screenshot').wait_for(state='visible')
    assert page.evaluate('window.captureSerial')=='emulator-5554'
    assert panel.locator('#screenshot').evaluate('node=>node.complete&&node.naturalWidth>0')
    panel.locator('#close-screen').click();panel.locator('#screen').wait_for(state='hidden')
   else:
    page.clock.fast_forward(31000)
    assert 'Elapsed · refresh to verify' in panel.locator('#rows').inner_text()
    assert panel.locator('.held').count()==1
    assert panel.locator('.free').count()==1
   page.evaluate('window.fail=true');panel.locator('#refresh').click()
   panel.locator('#error').wait_for(state='visible')
   assert 'last successful snapshot' in panel.locator('#error').inner_text()
   assert panel.locator('#rows tr').count()==rows
   page.evaluate('window.fail=false')
   calls=page.evaluate('window.calls')
   captures=page.evaluate('window.captures')
   panel.locator('#auto').check();page.clock.fast_forward(11000)
   page.wait_for_function(f'window.calls === {calls+1}')
   expect(panel.locator('#refresh')).to_be_enabled()
   panel.locator('#auto').uncheck();page.clock.fast_forward(11000)
   assert page.evaluate('window.calls')==calls+1
   assert page.evaluate('window.captures')==captures, 'Auto-refresh must not capture screenshots'
   key='emulators' if mode=='emulator' else 'devices'
   # A hostile device/owner label must remain text in the rendered table.
   page.evaluate("window.snapshot."+key+"[0]."+('name' if mode=='emulator' else 'model')+" = '<img src=x onerror=window.injected=true>';window.sendSnapshot()")
   assert panel.locator('#rows img').count()==0
   page.evaluate('window.snapshot.'+key+'=[];window.sendSnapshot()')
   panel.locator('#empty').wait_for(state='visible')
   assert 'No ' in panel.locator('#empty').inner_text()
   page.evaluate("window.snapshot.adb={state:'unavailable',detail:'ADB probe timed out'};window.sendSnapshot()")
   panel.locator('#empty').get_by_text('ADB probe timed out',exact=True).wait_for()
   page.evaluate('window.snapshot='+json.dumps(SNAPSHOTS[mode])+';window.sendSnapshot()')
   expect(panel.locator('#rows tr')).to_have_count(rows)
   page.set_viewport_size({'width':390,'height':844})
   assert panel.locator('main').evaluate('node=>node.scrollWidth<=node.clientWidth')
   page.evaluate("document.getElementById('panel').contentWindow.postMessage({jsonrpc:'2.0',method:'ui/notifications/host-context-changed',params:{theme:'dark'}},'*')")
   page.wait_for_timeout(100);assert panel.locator('html').get_attribute('data-theme')=='dark'
   assert not errors,errors
   page.close();print(f'PASS: {mode} initial snapshot, refresh, filter, read-only actions, escaping, errors, empty states, responsive layout, and theme')
  browser.close()
finally:server.shutdown();server.server_close();thread.join()
