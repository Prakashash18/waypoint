"""Record the animated opening as a video segment.

The sequence is a CSS timeline, so it is recorded rather than screenshotted —
the words arrive with the narration instead of cutting between stills.
"""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTRO, VID = os.path.join(ROOT, 'demo', 'intro'), os.path.join(ROOT, 'demo', 'video')
SECONDS = float(os.getenv('INTRO_SECONDS', '15.5'))

os.makedirs(VID, exist_ok=True)
tmp = os.path.join(VID, '_intro_take')
os.makedirs(tmp, exist_ok=True)

with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={'width': 1280, 'height': 800},
                        record_video_dir=tmp,
                        record_video_size={'width': 1280, 'height': 800})
    p = ctx.new_page()
    p.goto('file://' + os.path.join(INTRO, 'intro.html'))
    p.wait_for_timeout(int(SECONDS * 1000))
    p.screenshot(path=os.path.join(INTRO, 'intro.png'))   # a still for thumbnails
    raw = p.video.path()
    ctx.close(); b.close()

out = os.path.join(VID, 'intro.mp4')
subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', raw,
                '-vf', 'scale=1280:800,fps=30,format=yuv420p',
                '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', out], check=True)
for f in os.listdir(tmp):
    os.remove(os.path.join(tmp, f))
os.rmdir(tmp)
print('opening:', out, f'({SECONDS:.1f}s)')
