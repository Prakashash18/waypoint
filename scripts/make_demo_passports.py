"""Generate specimen passport images for demonstrating the scanner.

These are fixtures, not facsimiles. They carry a genuine ICAO machine-readable
zone — correct field layout and correct check digits, computed by the same
parser the app uses — so a demo exercises the real code path rather than a
mock. Everything else is deliberately unlike a real passport: a plain layout,
no security artwork, an obvious watermark, and invented names and numbers.

Regenerate with:  venv/bin/python scripts/make_demo_passports.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageFont          # noqa: E402  (dev-only)

from src.tools.mrz import check_digit, parse         # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'demo', 'passports')

# Two adults, to match a two-traveller trip. Invented people, invented numbers.
PEOPLE = [
    {'surname': 'TAN', 'given': 'WEI MING', 'sex': 'M', 'dob': '900115',
     'number': 'E1234567A', 'expires': '320415', 'country': 'SGP',
     'dob_text': '15 JAN 1990', 'exp_text': '15 APR 2032', 'file': 'traveller-1-tan-wei-ming'},
    {'surname': 'LEE', 'given': 'SU YIN', 'sex': 'F', 'dob': '920505',
     'number': 'E7654321B', 'expires': '310820', 'country': 'SGP',
     'dob_text': '05 MAY 1992', 'exp_text': '20 AUG 2031', 'file': 'traveller-2-lee-su-yin'},
]

INK, MUTED, PAPER, BAND = (26, 24, 21), (122, 113, 104), (244, 241, 234), (252, 251, 249)
ACCENT = (150, 74, 48)


def font(paths, size):
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


MONO = ['/System/Library/Fonts/Menlo.ttc', '/System/Library/Fonts/Courier.ttc',
        '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf']
SANS = ['/System/Library/Fonts/Helvetica.ttc',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']


def mrz_lines(p):
    """Build a TD3 zone, with every check digit computed rather than typed."""
    name = f"{p['surname']}<<{p['given'].replace(' ', '<')}"
    l1 = f"P<{p['country']}{name}".ljust(44, '<')[:44]

    num = p['number'].ljust(9, '<')
    optional = '<' * 14
    body = (num + str(check_digit(num)) + p['country']
            + p['dob'] + str(check_digit(p['dob'])) + p['sex']
            + p['expires'] + str(check_digit(p['expires'])) + optional
            + str(check_digit(optional)))
    composite = (num + str(check_digit(num)) + p['dob'] + str(check_digit(p['dob']))
                 + p['expires'] + str(check_digit(p['expires']))
                 + optional + str(check_digit(optional)))
    return l1, body + str(check_digit(composite))


def draw(p):
    W, H = 1360, 860
    img = Image.new('RGB', (W, H), (232, 228, 220))
    d = ImageDraw.Draw(img)

    d.rounded_rectangle([28, 28, W - 28, H - 28], radius=26, fill=PAPER)

    f_title = font(SANS, 40)
    f_label = font(SANS, 21)
    f_value = font(SANS, 33)
    f_small = font(SANS, 20)
    f_mono = font(MONO, 41)

    d.text((70, 66), 'SPECIMEN TRAVEL DOCUMENT', font=f_title, fill=INK)
    d.text((70, 118), 'Issued by no authority · for software demonstration only',
           font=f_small, fill=MUTED)

    d.rounded_rectangle([W - 300, 62, W - 70, 108], radius=10, fill=(247, 226, 216))
    d.text((W - 284, 74), 'NOT A REAL PASSPORT', font=f_small, fill=ACCENT)

    # Portrait placeholder — plainly a placeholder.
    d.rounded_rectangle([70, 190, 320, 520], radius=12, fill=(226, 221, 212))
    d.ellipse([160, 250, 230, 320], fill=(198, 191, 181))
    d.ellipse([140, 340, 250, 470], fill=(198, 191, 181))
    d.text((110, 540), 'no photograph', font=f_small, fill=MUTED)

    # Two columns, so seven fields clear the machine-readable band below.
    cols = [[('Surname', p['surname']),
             ('Given names', p['given']),
             ('Nationality', 'SINGAPORE (SGP)'),
             ('Document no.', p['number'])],
            [('Date of birth', p['dob_text']),
             ('Sex', p['sex']),
             ('Date of expiry', p['exp_text'])]]
    for col, rows in enumerate(cols):
        x = 380 + col * 480
        y = 195
        for label, value in rows:
            d.text((x, y), label.upper(), font=f_label, fill=MUTED)
            d.text((x, y + 26), value, font=f_value, fill=INK)
            y += 108

    # The machine-readable zone — the only part the app reads.
    l1, l2 = mrz_lines(p)
    d.rounded_rectangle([70, 690, W - 70, 806], radius=10, fill=BAND,
                        outline=(222, 216, 206))
    d.text((92, 706), l1, font=f_mono, fill=(14, 14, 14))
    d.text((92, 757), l2, font=f_mono, fill=(14, 14, 14))

    # Watermark, so the image cannot be mistaken for a document at a glance.
    mark = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    md = ImageDraw.Draw(mark)
    md.text((250, 400), 'SPECIMEN', font=font(SANS, 190), fill=(150, 74, 48, 38))
    img = Image.alpha_composite(img.convert('RGBA'), mark.rotate(20, center=(W // 2, H // 2))
                                ).convert('RGB')

    path = os.path.join(OUT, f"{p['file']}.png")
    img.save(path, optimize=True)
    return path, (l1, l2)


def main():
    os.makedirs(OUT, exist_ok=True)
    for p in PEOPLE:
        path, lines = draw(p)
        result = parse(list(lines))
        f = result.fields
        ok = result.ok and not f['expired']
        print(f"{'OK ' if ok else 'BAD'} {os.path.basename(path)}")
        print(f"     {f['name']} · {f['document_number']} · born {f['birthday']} "
              f"· {f['gender']} · {f['nationality']} · expires {f['expires']}")
        if result.failed:
            print('     failed checks:', result.failed)


if __name__ == '__main__':
    main()
