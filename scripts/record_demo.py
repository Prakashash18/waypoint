"""Drive the demo end to end and record it.

Playwright is already a dependency here (it takes the hotel screenshots), and
it records video natively, so the capture is a real screen recording at a
steady frame rate rather than stitched stills.

Nothing is faked: this drives the live app against live APIs, so what lands in
the file is what a judge would see. That also means the raw take runs at real
API speed — squeeze the waits afterwards rather than pretending they are not
there.

    venv/bin/python scripts/record_demo.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.sync_api import sync_playwright   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'demo', 'video')
PASSPORTS = os.path.join(ROOT, 'demo', 'passports')
APP = os.getenv('WAYPOINT_URL', 'http://localhost:2000/app')

ASK = 'Four nights in Ubud Bali 28 Sep to 2 Oct 2026, two adults, with flights'


MARKS = []
_T0 = [0.0]


def beat(page, label, ms=1200):
    """A pause to let the eye land, and a note of where we are.

    The elapsed time is recorded so narration can be cut against the frames it
    actually describes, rather than against a guess.
    """
    at = time.time() - _T0[0]
    MARKS.append({'at': round(at, 2), 'label': label})
    print(f'  {at:6.1f}s  {label}')
    page.wait_for_timeout(ms)


def run(page):
    page.goto(APP, wait_until='networkidle')
    _T0[0] = time.time()
    beat(page, 'the empty state', 2200)

    # ── the ask ──────────────────────────────────────────────────
    box = page.locator('textarea').first
    box.click()
    box.type(ASK, delay=38)          # typed, so the viewer reads it forming
    beat(page, 'question typed', 900)
    page.get_by_role('button', name='Plan trip').click()

    # ── the agent working in the open ────────────────────────────
    page.wait_for_selector('.hud', timeout=20_000)
    beat(page, 'HUD streaming real calls', 4000)
    page.wait_for_selector('.combo', timeout=180_000)
    beat(page, 'three trips priced', 3500)

    # Let the provenance line land — the "we do not invent" beat.
    page.mouse.wheel(0, 520)
    beat(page, 'whole-trip pricing + provenance', 3000)
    page.mouse.wheel(0, -520)
    beat(page, 'back to the cards', 800)

    # ── choose, then book ────────────────────────────────────────
    page.locator('button', has_text='See this trip').first.click()
    page.wait_for_selector('.chosen-card', timeout=30_000)
    beat(page, 'the chosen trip', 2600)

    book = page.locator('button', has_text='Book this flight').first
    if not book.count():
        book = page.locator('button', has_text='Book the flight').first
    book.click()

    page.wait_for_selector('.sheet.is-booking', timeout=30_000)
    page.wait_for_selector('.booking-steps li.is-ok', timeout=60_000)
    beat(page, 'fare re-verified with the airline', 3200)

    # ── baggage, and the total following the choice ──────────────
    bags = page.locator('.bagopt')
    if bags.count():
        bags.first.click()
        page.wait_for_timeout(6000)
        beat(page, 'baggage added, total moves', 2400)

    # ── answering by keyboard ────────────────────────────────────
    page.locator('.booking-type').fill('yes')
    beat(page, 'answering "yes"', 700)
    page.locator('.booking-typed button[type=submit]').click()
    page.wait_for_selector('.paxform', timeout=20_000)
    beat(page, 'who is flying', 1600)

    # ── the passports: the moment worth the whole demo ───────────
    shots = sorted(f for f in os.listdir(PASSPORTS) if f.endswith('.png'))
    for i, name in enumerate(shots[:2]):
        drop = page.locator('.ppdrop input[type=file]').nth(i)
        drop.set_input_files(os.path.join(PASSPORTS, name))
        page.wait_for_timeout(9000)
        beat(page, f'passport {i + 1} read → fields filled', 2200)

    # Contact details are the only thing a passport cannot supply.
    rows = page.locator('.paxrow')
    contact = rows.nth(rows.count() - 1)
    contact.locator('input[type=text]').first.fill('TAN/WEI MING')
    contact.locator('input[type=email]').fill('tan@example.com')
    contact.locator('input[type=tel]').fill('0065-91234567')
    beat(page, 'contact details', 1500)

    # ── the order ────────────────────────────────────────────────
    page.locator('.paxform button', has_text='Create the order').click()
    page.wait_for_selector('.ordered', timeout=90_000)
    beat(page, 'ORDER CREATED — seats held', 4000)
    page.mouse.wheel(0, 420)
    beat(page, 'paying stays with the traveller', 4500)


def main():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--force-color-profile=srgb'])
        ctx = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            device_scale_factor=2,
            color_scheme='light',
            record_video_dir=OUT,
            record_video_size={'width': 1280, 'height': 800},
        )
        page = ctx.new_page()
        try:
            run(page)
        except Exception as exc:
            print(f'\n  ! stopped: {exc}\n')
        finally:
            path = page.video.path() if page.video else None
            ctx.close()
            browser.close()
            if path:
                marks = os.path.join(OUT, 'marks.json')
                with open(marks, 'w') as fh:
                    json.dump(MARKS, fh, indent=1)
                print('\nraw take:', path)
                print('beat times:', marks)


if __name__ == '__main__':
    main()
