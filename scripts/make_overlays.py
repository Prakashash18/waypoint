"""Render the callout overlays that label parts of the app on screen.

Each is a small card in the product's own type and palette, rendered once by
the browser and composited over the recording. They are cued from the beat
timings, so a label names whatever is actually on screen underneath it.
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from playwright.sync_api import sync_playwright        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'demo', 'overlays')

# label, supporting line, beat it belongs to, seconds on screen, corner
CALLOUTS = [
    ('The agent, working in the open',
     'Every line is a real API call — arguments, result, milliseconds',
     'HUD streaming real calls', 7.5, 'tr'),
    ('One price for the whole trip',
     'Both fares + every night + taxes — not a per-person teaser',
     'three trips priced', 7.0, 'tr'),
    ('Where every figure came from',
     'Each provider named, each timing shown, gaps admitted',
     'live sources named', 7.5, 'tr'),
    ('The property’s own photograph',
     'From its listing — never a stock image, never a guess',
     'exploring the stay', 6.5, 'tr'),
    ('Ask anything, answered on the map',
     'Real places nearby, each opening Google Maps walking directions',
     'real places nearby, each with walking directions', 7.5, 'tr'),
    ('Atlas holds the seats',
     'Fare re-verified, baggage priced per traveller per leg',
     'fare re-verified with the airline', 7.0, 'tr'),
    ('The passport fills the form',
     'Machine-readable zone, every check digit verified',
     'who is flying', 8.0, 'tr'),
    ('A real order, holding real seats',
     'Payment deadline running — and payment left to you',
     'ORDER CREATED — seats held', 7.5, 'tr'),
]

CARD = """
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600&family=Inter:wght@400;500;600&display=swap');
  html,body{margin:0;background:transparent}
  .card{
    display:inline-block;max-width:470px;padding:17px 21px;
    background:rgba(28,25,23,.93);border:1px solid rgba(224,138,104,.42);
    border-radius:14px;box-shadow:0 10px 34px rgba(0,0,0,.32);
    font-family:Inter,system-ui,sans-serif;
  }
  .t{font:600 21px/1.25 Fraunces,Georgia,serif;color:#f4efe7;margin-bottom:6px}
  .s{font-size:15px;line-height:1.45;color:#c3b8ab}
  .rule{height:2px;width:34px;background:#e08a68;border-radius:2px;margin-bottom:12px}
</style>
<div class="card"><div class="rule"></div>
  <div class="t">%s</div><div class="s">%s</div>
</div>
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    marks = {m['label']: m['at'] for m in
             json.load(open(os.path.join(ROOT, 'demo', 'video', 'marks.json')))}
    cues = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_context(viewport={'width': 560, 'height': 240},
                             device_scale_factor=2).new_page()
        for i, (title, sub, beat, hold, corner) in enumerate(CALLOUTS):
            if beat not in marks:
                print(f'  skipped (no such beat): {beat}')
                continue
            page.set_content(CARD % (title, sub))
            page.wait_for_timeout(320)
            path = os.path.join(OUT, f'c{i:02d}.png')
            page.locator('.card').screenshot(path=path, omit_background=True)
            cues.append({'png': path, 'at': marks[beat], 'hold': hold, 'corner': corner})
            print(f'  {marks[beat]:6.1f}s  {title}')
        b.close()

    with open(os.path.join(OUT, 'cues.json'), 'w') as fh:
        json.dump(cues, fh, indent=1)
    print(f'\n  {len(cues)} callouts')


if __name__ == '__main__':
    main()
