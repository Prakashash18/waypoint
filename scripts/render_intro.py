"""Render the intro slide to a still and a short video segment."""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTRO = os.path.join(ROOT, 'demo', 'intro')
SECONDS = float(os.getenv('INTRO_SECONDS', '11'))

with sync_playwright() as pw:
    b = pw.chromium.launch()
    p = b.new_context(viewport={'width': 1280, 'height': 800},
                      device_scale_factor=2).new_page()
    p.goto('file://' + os.path.join(INTRO, 'intro.html'))
    p.wait_for_timeout(1600)                    # let the fonts and fade settle
    p.screenshot(path=os.path.join(INTRO, 'intro.png'))
    b.close()

# A still image is a steadier opening than a re-recorded animation, and it
# holds exactly as long as the narration needs.
out = os.path.join(ROOT, 'demo', 'video', 'intro.mp4')
subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-loop', '1',
                '-i', os.path.join(INTRO, 'intro.png'), '-t', str(SECONDS),
                '-vf', 'scale=1280:800,fps=30,format=yuv420p',
                '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', out], check=True)
print('intro still :', os.path.join(INTRO, 'intro.png'))
print('intro clip  :', out, f'({SECONDS:.0f}s)')
