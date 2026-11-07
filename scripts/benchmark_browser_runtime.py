"""Measure a running Eureka gateway using real browser/PCM; no model substitution."""
import argparse
import json
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path


def main():
    import httpx
    from playwright.sync_api import sync_playwright
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--label', default='runtime')
    parser.add_argument('--frontend-from-checkout', action='store_true')
    parser.add_argument('--check-cancel', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = root / 'orther/artifacts/tts-upgrade-20261107' / (args.label + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(parents=True, exist_ok=False)
    health = httpx.get(args.url.rstrip('/') + '/health/ready', timeout=45).json()
    (out / 'health.json').write_text(json.dumps(health, ensure_ascii=False, indent=2), encoding='utf-8')
    rows = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page(viewport={'width': 1100, 'height': 850})
        if args.frontend_from_checkout:
            assets = root / 'app/voice_app/web_assets'
            (out/'frontend-source.json').write_text(json.dumps({name:hashlib.sha256((assets/name).read_bytes()).hexdigest()
                                                               for name in ('index.html','app.js','style.css')},indent=2),encoding='utf-8')
            page.route(args.url.rstrip('/')+'/', lambda route: route.fulfill(path=str(assets/'index.html'), content_type='text/html'))
            page.route('**/assets/app.js?*', lambda route: route.fulfill(path=str(assets/'app.js'), content_type='text/javascript'))
            page.route('**/assets/style.css?*', lambda route: route.fulfill(path=str(assets/'style.css'), content_type='text/css'))
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(args.url, wait_until='domcontentloaded', timeout=60000)
        page.wait_for_function("typeof handleEvent === 'function'", timeout=30000)
        if args.frontend_from_checkout:
            page.wait_for_function("!document.querySelector('#voiceIndex').disabled", timeout=30000)
        page.evaluate("""() => {
          window.__benchmarkEvents=[];
          const original=handleEvent;
          handleEvent=(event,...rest)=>{
            window.__benchmarkEvents.push({...event,browser_observed_ms:performance.now()});
            original(event,...rest);
          };
        }""")
        for index in range(args.runs):
            start = time.monotonic()
            page.evaluate('window.__benchmarkEvents=[]')
            page.locator('#question').fill('Xin chào.')
            page.locator('#sendBtn').click()
            try:
                page.wait_for_function('serverTurnDone && playbackDrained && !turnBusy', timeout=180000)
                error = None
            except Exception as exc:
                error = str(exc)
            row = page.evaluate("""() => ({browser:bm,events:window.__benchmarkEvents,
              status:document.querySelector('#status').textContent,
              answer:document.querySelector('.message.assistant:last-of-type')?.textContent,
              turnBusy,playbackDrained,serverTurnDone})""")
            row.update(run=index+1, elapsed_seconds=time.monotonic()-start, error=error,
                       frontend='local checkout assets against live remote backend' if args.frontend_from_checkout else 'served by live gateway',
                       boundary='browser request to PCM receive; worklet consumption is not a physical speaker measurement',
                       page_errors=list(errors))
            rows.append(row)
            (out / 'results.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
            page.screenshot(path=str(out / f'run-{index+1}.png'), full_page=True)
            metrics = next((e.get('meta', {}) for e in row['events'] if e.get('type') == 'done'), {})
            units = [e for e in row['events'] if e.get('type') == 'tts_unit_done']
            print(json.dumps({'run':index+1,'error':error,'first_browser_pcm_ms':row['browser'].get('first_pcm_received_ms'),
                              'units':units,'pipeline':metrics,'out':str(out)}, ensure_ascii=False), flush=True)
            if error:
                break
        if args.check_cancel:
            page.locator('#question').fill('Xin chào.')
            page.locator('#sendBtn').click()
            page.wait_for_function('bm.first_audio_started_estimate_ms !== null && currentTurn !== null', timeout=60000)
            turn = page.evaluate('currentTurn')
            page.locator('#interruptBtn').click()
            page.wait_for_function('!turnBusy && currentTurn === null', timeout=10000)
            # A subsequent real turn also tests that a disconnected TTS stream
            # released its slot instead of leaving the model busy indefinitely.
            page.locator('#question').fill('Xin chào.')
            page.locator('#sendBtn').click()
            page.wait_for_function('serverTurnDone && playbackDrained && !turnBusy', timeout=120000)
            cancel = {'cancelled_turn':httpx.get(args.url.rstrip('/')+'/api/turn/'+turn,timeout=30).json(),
                      'next_turn':page.evaluate('({turnFailure,serverTurnDone,playbackDrained,browser:bm})'),
                      'frontend':'checkout' if args.frontend_from_checkout else 'live','page_errors':errors}
            (out/'cancel-and-resume.json').write_text(json.dumps(cancel,ensure_ascii=False,indent=2),encoding='utf-8')
            assert cancel['next_turn']['turnFailure'] is None and cancel['next_turn']['playbackDrained']
        browser.close()


if __name__ == '__main__':
    main()
