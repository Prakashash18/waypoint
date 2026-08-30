"""Assemble the submission: intro slide, screen recording, narration.

Narration is placed against the beat timings the recorder logged, so each line
lands on the frames it actually describes rather than on an estimate.

    venv/bin/python scripts/build_video.py
"""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VID, AUD = os.path.join(ROOT, 'demo', 'video'), os.path.join(ROOT, 'demo', 'audio')
OUT = os.path.join(VID, 'waypoint-demo.mp4')


def sh(args):
    subprocess.run(args, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def dur(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                          'format=duration', '-of', 'default=nw=1:nk=1', path],
                         capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def main():
    raw = max((os.path.join(VID, f) for f in os.listdir(VID) if f.endswith('.webm')),
              key=os.path.getmtime)
    marks = {m['label']: m['at'] for m in
             json.load(open(os.path.join(VID, 'marks.json')))}
    intro_cues = json.load(open(os.path.join(VID, 'intro_cues.json')))

    intro_mp4 = os.path.join(VID, 'intro.mp4')
    if not os.path.exists(intro_mp4):
        sys.exit('Run scripts/render_intro.py first — the opening is missing.')
    intro_len = dur(intro_mp4)

    # The recording is webm; normalise both to the same codec before joining.
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-i', raw,
        '-vf', 'scale=1280:800,fps=30,format=yuv420p',
        '-c:v', 'libx264', '-preset', 'slow', '-crf', '18',
        os.path.join(VID, 'body.mp4')])

    listing = os.path.join(VID, 'parts.txt')
    with open(listing, 'w') as fh:
        fh.write(f"file '{intro_mp4}'\n")
        fh.write(f"file '{os.path.join(VID, 'body.mp4')}'\n")
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0',
        '-i', listing, '-c', 'copy', os.path.join(VID, 'silent.mp4')])

    # Narration: each line is anchored to the beat it describes. Anchors alone
    # let two lines collide when the beats are closer together than the lines
    # are long — which is exactly what happened — so a line never starts before
    # the previous one has finished, plus a breath.
    ANCHORS = [
        ('01a-problem',  'INTRO'),
        ('01b-claim',    'INTRO'),
        ('01c-booking',  'INTRO'),
        ('02-ask',      'the empty state'),
        ('03-work',     'HUD streaming real calls'),
        ('04-cards',    'three trips priced'),
        ('05-sources',  'live sources named'),
        ('06-stay',     'exploring the stay'),
        ('07-nearby',   'every one opens Google Maps from the stay'),
        ('08-book',     'fare re-verified with the airline'),
        ('09-passport', 'who is flying'),
        ('10-order',    'ORDER CREATED — seats held'),
    ]
    GAP = 0.2

    CUES, free = [], 0.0
    for name, label in ANCHORS:
        if label == 'INTRO':
            # Placed by the opening's own generated timeline, so the voice and
            # the panel it belongs to start together.
            anchor = intro_cues[name]
        else:
            anchor = intro_len + marks[label]
        at = max(anchor, free)
        CUES.append((name, at))
        free = at + dur(os.path.join(AUD, f'{name}.mp3')) + GAP

    body_len = dur(raw)
    if free > intro_len + body_len:
        print(f'  ! narration runs {free - (intro_len + body_len):.1f}s past the picture')

    inputs, filters, mixes = ['-i', os.path.join(VID, 'silent.mp4')], [], []
    for i, (name, offset) in enumerate(CUES):
        inputs += ['-i', os.path.join(AUD, f'{name}.mp3')]
        filters.append(f'[{i + 1}:a]adelay={int(offset * 1000)}|{int(offset * 1000)}[a{i}]')
        mixes.append(f'[a{i}]')
    graph = (';'.join(filters) + ';' + ''.join(mixes)
             + f'amix=inputs={len(CUES)}:normalize=0[out]')

    sh(['ffmpeg', '-y', '-loglevel', 'error', *inputs,
        '-filter_complex', graph, '-map', '0:v', '-map', '[out]',
        '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', OUT])

    for tmp in ('body.mp4', 'silent.mp4', 'parts.txt'):
        os.remove(os.path.join(VID, tmp))

    total = dur(OUT)
    print(f'\n  {OUT}')
    print(f'  {total:.0f}s  ({total / 60:.1f} min of a 3:00 budget)')
    prev_end = 0.0
    for name, off in CUES:
        end = off + dur(os.path.join(AUD, f'{name}.mp3'))
        clash = '  OVERLAP' if off < prev_end - 0.01 else ''
        print(f'    {off:6.1f}s → {end:6.1f}s  {name}{clash}')
        prev_end = end


if __name__ == '__main__':
    sys.exit(main())
