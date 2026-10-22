# /// script
# requires-python = ">=3.12"
# dependencies = ["playwright==1.62.0", "psutil==7.1.0"]
# ///
"""Opt-in browser verification of the source panel with actual VM status/frames."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from guest_config import load
from guest_registry import entries, state
from guest_screen import capture
from status import collect_status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, action='append', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--chromium', default=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE'))
    args = parser.parse_args()
    configs = [load(path) for path in args.profile]
    guests = [next(entry for entry in entries() if entry['state_dir'] == c['state_dir']) for c in configs]
    if any(state(guest)[0] != 'ready' for guest in guests):
        parser.error('Selected work VMs must already be ready')
    graphical = [guest for guest in guests if guest['graphical']]
    if not graphical:
        parser.error('Select at least one graphical VM')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    frames = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/snapshot':
                data, mime = json.dumps(collect_status()).encode(), 'application/json'
            else:
                name = 'status-panel.html' if self.path == '/panel' else 'live-panel-host.html'
                data, mime = (ROOT / 'templates' / name).read_bytes(), 'text/html; charset=utf-8'
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            try:
                if request['name'] == 'qemu_guest_screen':
                    value = capture(request['arguments']['guest_id'])
                    frames[value['guestId']] = 'data:image/png;base64,' + value['data']
                elif request['name'] == 'qemu_docker_status':
                    value = collect_status()
                else:
                    raise ValueError('Unknown tool')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(value).encode())
            except (OSError, ValueError, RuntimeError):
                self.send_error(503)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    report = {'passed': False, 'screens': []}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, executable_path=args.chromium)
            try:
                page = browser.new_page(viewport={'width': 1300, 'height': 1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}/')
                panel = page.frame_locator('#panel')
                for guest in guests:
                    card = panel.locator(f'#work-guests article[data-guest-id="{guest["id"]}"]')
                    card.wait_for()
                    assert 'ready' in card.inner_text()
                    assert f"{guest['cpus']} vCPU" in card.inner_text()
                    if not guest['graphical']:
                        assert card.get_by_role('button').count() == 0
                screen_sequence = [*graphical, graphical[0]] if len(graphical) > 1 else graphical
                for index, guest in enumerate(screen_sequence):
                    panel.locator(f'#work-guests article[data-guest-id="{guest["id"]}"]').get_by_role('button').click()
                    panel.locator('#screen-title').filter(has_text=guest['name']).wait_for()
                    panel.locator('#work-screen').wait_for(state='visible')
                    page.wait_for_function("document.querySelector('iframe').contentDocument.querySelector('#work-screen').naturalWidth > 100")
                    image = panel.locator('#work-screen').get_attribute('src')
                    assert image == frames[guest['id']], 'Panel displayed a different VM frame'
                    panel.locator('body').screenshot(path=str(args.output_dir / f'panel-{index}.png'))
                    report['screens'].append({'name': guest['name'], 'frameMatchesGuest': True})
                assert not errors, errors
                report.update(passed=True,
                    headlessHasNoScreenButton=True if len(graphical) < len(guests) else None,
                    screenSwitchingVerified=len(graphical) > 1, browserErrors=errors)
            finally:
                browser.close()
        print('PASS: selected live status cards and graphical VM frames; see report for exercised coverage')
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        (args.output_dir / 'report.json').write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
