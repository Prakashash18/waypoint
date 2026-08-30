"""Build and record the animated opening, timed to the narration.

The panels used to run on hand-written CSS delays while the voice ran on its
own length, so a beat could change while its sentence was still being spoken.
The timeline is now generated from the measured audio: each panel is held for
as long as its own line takes, plus a breath, and the words inside it are
staggered across the first part of that hold.
"""
import os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from playwright.sync_api import sync_playwright        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTRO, VID, AUD = (os.path.join(ROOT, 'demo', 'intro'),
                   os.path.join(ROOT, 'demo', 'video'),
                   os.path.join(ROOT, 'demo', 'audio'))
PAD = 0.25           # a breath after each line before the panel changes
LEAD = 0.5           # the panel arrives just before the voice does


def dur(name):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                          '-of', 'default=nw=1:nk=1', os.path.join(AUD, f'{name}.mp3')],
                         capture_output=True, text=True).stdout.strip()
    return float(out or 0)


HEADLINE = 'Most travel agents stop at the'.split() + ['recommendation.']
CLAIM = 'This one stops at your wallet.'.split()


def build():
    # The closing panel carries no line — the three promises are legible on
    # screen, and the demo spends the next two minutes proving them.
    beats = [('01a-problem', dur('01a-problem')), ('01b-claim', dur('01b-claim')),
             ('01c-booking', dur('01c-booking')), ('01d-promises', 3.0)]

    starts, t, cues = [], 0.0, {}
    for name, d in beats:
        starts.append(t)
        cues[name] = t
        t += d + PAD
    total = t
    b1, b2, b3, b4 = starts

    # Words land across the first 60% of their panel, never past its line.
    def stagger(words, start, span):
        step = span / max(len(words), 1)
        return [start + i * step for i in range(len(words))]

    h_at = stagger(HEADLINE, b1 + 0.25, min(1.9, dur('01a-problem') * 0.7))
    c_at = stagger(CLAIM, b2 + 0.25, 1.5)

    words_h = '\n      '.join(
        f'<span class="w{" strike" if w == "recommendation." else ""}" '
        f'style="animation-delay:{a:.2f}s">{w}</span>'
        for w, a in zip(HEADLINE, h_at))
    words_c = '\n      '.join(
        f'<span class="w" style="animation-delay:{a:.2f}s">{w}</span>'
        for w, a in zip(CLAIM, c_at))

    css = f"""
  #b1{{animation:hold {beats[0][1] + PAD:.2f}s ease-in-out {b1:.2f}s forwards}}
  #b1 .strike::after{{animation:wipe .45s ease-out {h_at[-1] + 0.45:.2f}s forwards}}
  #b2{{animation:hold {beats[1][1] + PAD:.2f}s ease-in-out {b2 - LEAD:.2f}s forwards}}
  #b2 .sub{{animation:rise .6s ease-out {c_at[-1] + 0.5:.2f}s forwards}}
  #bk{{animation:hold {beats[2][1] + PAD:.2f}s ease-in-out {b3 - LEAD:.2f}s forwards}}
  #bk h3{{animation:rise .5s ease-out {b3 - 0.2:.2f}s forwards}}
  .lane:nth-child(1){{animation-delay:{b3 + 1.4:.2f}s}}
  .lane:nth-child(2){{animation-delay:{b3 + 6.4:.2f}s}}
  .lane:nth-child(1) .flow span:nth-child(1){{animation-delay:{b3 + 2.4:.2f}s}}
  .lane:nth-child(1) .flow span:nth-child(2){{animation-delay:{b3 + 3.1:.2f}s}}
  .lane:nth-child(1) .flow span:nth-child(3){{animation-delay:{b3 + 3.8:.2f}s}}
  .lane:nth-child(2) .flow span:nth-child(1){{animation-delay:{b3 + 8.2:.2f}s}}
  .lane:nth-child(2) .flow span:nth-child(2){{animation-delay:{b3 + 9.0:.2f}s}}
  #b3{{animation:hold {beats[3][1] + PAD + 0.6:.2f}s ease-in-out {b4 - LEAD:.2f}s forwards}}
  .three>div:nth-child(1){{animation-delay:{b4 + 0.1:.2f}s}}
  .three>div:nth-child(2){{animation-delay:{b4 + 1.2:.2f}s}}
  .three>div:nth-child(3){{animation-delay:{b4 + 2.3:.2f}s}}
  .foot{{animation:rise .6s ease-out {b4 + 2.9:.2f}s forwards}}
"""
    src = open(os.path.join(INTRO, 'intro.template.html')).read()
    html = (src.replace('/*TIMELINE*/', css)
               .replace('<!--HEADLINE-->', words_h)
               .replace('<!--CLAIM-->', words_c))
    open(os.path.join(INTRO, 'intro.html'), 'w').write(html)
    return total, cues


def main():
    total, cues = build()
    tmp = os.path.join(VID, '_intro_take')
    os.makedirs(tmp, exist_ok=True)
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={'width': 1280, 'height': 800},
                            record_video_dir=tmp,
                            record_video_size={'width': 1280, 'height': 800})
        p = ctx.new_page()
        p.goto('file://' + os.path.join(INTRO, 'intro.html'))
        p.wait_for_timeout(int((total + 0.6) * 1000))
        raw = p.video.path()
        ctx.close(); b.close()

    out = os.path.join(VID, 'intro.mp4')
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', raw,
                    '-vf', 'scale=1280:800,fps=30,format=yuv420p',
                    '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', out], check=True)
    for f in os.listdir(tmp):
        os.remove(os.path.join(tmp, f))
    os.rmdir(tmp)

    import json
    json.dump(cues, open(os.path.join(VID, 'intro_cues.json'), 'w'), indent=1)
    print(f'opening: {out}  ({total:.1f}s)')
    for name, at in cues.items():
        print(f'   {at:5.1f}s  {name}')


if __name__ == '__main__':
    main()
