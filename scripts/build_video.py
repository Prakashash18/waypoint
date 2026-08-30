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

    intro_len = dur(os.path.join(AUD, '01-intro.mp3')) + 1.4    # a beat to read on
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-loop', '1',
        '-i', os.path.join(ROOT, 'demo', 'intro', 'intro.png'),
        '-t', f'{intro_len:.2f}', '-vf', 'scale=1280:800,fps=30,format=yuv420p',
        '-c:v', 'libx264', '-preset', 'slow', '-crf', '18',
        os.path.join(VID, 'intro.mp4')])

    # The recording is webm; normalise both to the same codec before joining.
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-i', raw,
        '-vf', 'scale=1280:800,fps=30,format=yuv420p',
        '-c:v', 'libx264', '-preset', 'slow', '-crf', '18',
        os.path.join(VID, 'body.mp4')])

    listing = os.path.join(VID, 'parts.txt')
    with open(listing, 'w') as fh:
        fh.write(f"file '{os.path.join(VID, 'intro.mp4')}'\n")
        fh.write(f"file '{os.path.join(VID, 'body.mp4')}'\n")
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0',
        '-i', listing, '-c', 'copy', os.path.join(VID, 'silent.mp4')])

    # Narration: line -> the beat it belongs on, offset into the joined timeline.
    CUES = [
        ('01-intro',    0.0),
        ('02-ask',      marks['the empty state']),
        ('03-work',     marks['HUD streaming real calls']),
        ('04-cards',    marks['three trips priced']),
        ('05-truth',    marks['whole-trip pricing + provenance']),
        ('06-book',     marks['fare re-verified with the airline']),
        ('07-passport', marks['who is flying']),
        ('08-order',    marks['ORDER CREATED — seats held']),
    ]

    inputs, filters, mixes = ['-i', os.path.join(VID, 'silent.mp4')], [], []
    for i, (name, at) in enumerate(CUES):
        # Everything after the intro sits on the far side of the slide.
        offset = at if name == '01-intro' else intro_len + at
        inputs += ['-i', os.path.join(AUD, f'{name}.mp3')]
        filters.append(f'[{i + 1}:a]adelay={int(offset * 1000)}|{int(offset * 1000)}[a{i}]')
        mixes.append(f'[a{i}]')
    graph = (';'.join(filters) + ';' + ''.join(mixes)
             + f'amix=inputs={len(CUES)}:normalize=0[out]')

    sh(['ffmpeg', '-y', '-loglevel', 'error', *inputs,
        '-filter_complex', graph, '-map', '0:v', '-map', '[out]',
        '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', OUT])

    for tmp in ('intro.mp4', 'body.mp4', 'silent.mp4', 'parts.txt'):
        os.remove(os.path.join(VID, tmp))

    total = dur(OUT)
    print(f'\n  {OUT}')
    print(f'  {total:.0f}s  ({total / 60:.1f} min of a 3:00 budget)')
    for name, at in CUES:
        off = at if name == '01-intro' else intro_len + at
        print(f'    {off:6.1f}s  {name}')


if __name__ == '__main__':
    sys.exit(main())
