"""Exercise the real catalogue and local comparison at a GitHub project subpath."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args): pass


def main():
    screenshots = ROOT / 'browser-checks'; screenshots.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        shutil.copytree(ROOT / 'dist', Path(temporary) / 'clamcounter')
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=temporary))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or None)
                page = browser.new_page(viewport={'width': 1280, 'height': 1000})
                errors = []; page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}/clamcounter/')
                page.locator('#results .card').first.wait_for()
                catalogue = json.loads((ROOT / 'web/data/catalogue.json').read_text())
                assert page.locator('#results .card').count() == len(catalogue['items'])
                page.locator('#search').fill('Tasty')
                assert page.locator('#results .card').count() == 1
                assert 'Two cups' in page.locator('#results').inner_text()
                page.locator('#results .compare').click()
                page.locator('#quantity').fill('2'); page.locator('#tax').check()
                assert '$34.09' in page.locator('#comparison-items').inner_text()
                page.locator('#save').click()
                page.locator('#quantity').fill('0')
                assert 'Order totals are unavailable' in page.locator('#comparison-items').inner_text()
                assert page.locator('#export-csv').is_disabled()
                page.locator('#quantity').fill('2')
                page.locator('#clear-comparison').click(); page.locator('#load').click()
                assert '$34.09' in page.locator('#comparison-items').inner_text()
                assert 'historical prices preserved' in page.locator('#comparison-note').inner_text()
                page.locator('#search').fill('Mic Mac'); page.locator('#results .compare').click()
                assert 'Ask for price' in page.locator('#comparison-items').inner_text()
                page.locator('#custom-name').fill('<img src=x onerror="alert(1)">')
                page.locator('#custom-price').fill('12.34'); page.locator('#custom-portion').fill('My phone quote, portion unknown')
                page.locator('#custom-form button').click()
                assert '<img src=x' in page.locator('#comparison-items').inner_text()
                assert page.locator('img').count() == 0
                assert '$28.14' in page.locator('#comparison-items').inner_text()
                with page.expect_download() as dl: page.locator('#export-json').click()
                exported = Path(temporary) / 'saved.json'; dl.value.save_as(exported)
                saved = json.loads(exported.read_text()); saved['items'][0]['cents'] = 1000
                saved['items'][0]['reviewed_at'] = '2025-01-01'; exported.write_text(json.dumps(saved))
                page.locator('#import').set_input_files(exported)
                assert '$22.80' in page.locator('#comparison-items').inner_text()
                assert '2025-01-01' in page.locator('#comparison-items').inner_text()
                page.locator('#search').fill(''); page.locator('#type').select_option('whole')
                assert page.locator('#results .card').count() == len([i for i in catalogue['items'] if i['type'] == 'whole'])
                page.locator('#results .favorite').first.click(); page.locator('#favorites').check()
                assert page.locator('#results .card').count() == 1
                page.locator('#reset').click()
                page.screenshot(path=str(screenshots / 'desktop.png'), full_page=True)
                page.set_viewport_size({'width': 390, 'height': 844})
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                page.screenshot(path=str(screenshots / 'mobile.png'), full_page=True)
                fixture = {'checked_at': '2026-11-25T01:00:00Z', 'sources': [{'id': 'palladium', 'status': 'needs_review'}, {'id': 'mic-mac', 'status': 'error'}]}
                page.route('**/data/status.json', lambda route: route.fulfill(json=fixture))
                page.reload(); page.locator('#results .card').first.wait_for()
                assert '1 source(s) changed' in page.locator('#monitor-status').inner_text()
                assert '1 source check(s) failed' in page.locator('#monitor-status').inner_text()
                page.locator('#search').fill('Mic Mac')
                assert 'Latest automated menu fetch failed' in page.locator('#results').inner_text()
                assert not errors, errors
                browser.close()
            print('Browser checks passed: project path, menu filters, exact totals, unknown prices, local save/import/export, safe text, source failures, mobile')
        finally: server.shutdown()


if __name__ == '__main__': main()
