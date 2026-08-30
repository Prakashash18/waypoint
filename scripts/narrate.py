"""Generate the video narration with ElevenLabs.

Same provider and key the app already speaks with, so the voice in the film is
the voice of the product. Segments are written separately and timed, so the cut
can be built around them rather than the other way round.

    venv/bin/python scripts/narrate.py
"""
import os, subprocess, sys
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, '.env'))
import requests                                              # noqa: E402

OUT = os.path.join(ROOT, 'demo', 'audio')
KEY = os.getenv('ELEVENLABS_API_KEY')
VOICE = os.getenv('WAYPOINT_NARRATOR', 'EXAVITQu4vr4xnSDxMaL')   # Sarah — warm, calm

SEGMENTS = [
    ('01-intro',
     'Most travel agents stop at the recommendation. This one stops at your wallet. '
     'Waypoint plans a whole trip by voice, books it for real, '
     'and refuses to invent a single thing along the way.'),
    ('02-ask',
     'You just say it, the way you would to a friend. '
     'Four nights in Ubud, two adults, with flights. '
     'It already knows you are flying from Singapore.'),
    ('03-work',
     'And then it works in the open. Every line here is a real API call — '
     'what was asked, what came back, how long it took. No spinner, no black box.'),
    ('04-cards',
     'Three real trips. Each price is the whole journey: both fares, every night, '
     'taxes included — matched against Booking dot com to the cent.'),
    ('05-truth',
     'When a source has nothing, it says so. It will not substitute a stock photograph '
     'or guess a price. Every figure on this screen carries where it came from.'),
    ('06-book',
     'Now it books. The fare is re-verified with the airline, baggage is priced per '
     'traveller per leg, and the total follows your choice.'),
    ('07-passport',
     'Passenger details come from the passport itself. It reads the machine-readable '
     'zone and checks every digit, so a misread is caught instead of ending up on a ticket.'),
    ('08-order',
     'And that is a real order, holding real seats, with a payment deadline. '
     'Everything except the payment — because moving your money should stay yours.'),
]


def say(name, text):
    r = requests.post(
        f'https://api.elevenlabs.io/v1/text-to-speech/{VOICE}',
        headers={'xi-api-key': KEY, 'Content-Type': 'application/json'},
        json={'text': text, 'model_id': 'eleven_turbo_v2_5',
              'voice_settings': {'stability': 0.45, 'similarity_boost': 0.75,
                                 'style': 0.15, 'use_speaker_boost': True}},
        timeout=90)
    r.raise_for_status()
    path = os.path.join(OUT, f'{name}.mp3')
    with open(path, 'wb') as fh:
        fh.write(r.content)
    dur = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'default=nw=1:nk=1', path],
        capture_output=True, text=True).stdout.strip()
    return path, float(dur or 0)


def main():
    if not KEY:
        print('ELEVENLABS_API_KEY is not set; narration skipped.')
        return 1
    os.makedirs(OUT, exist_ok=True)
    total = 0.0
    for name, text in SEGMENTS:
        path, dur = say(name, text)
        total += dur
        print(f'  {name:14} {dur:5.1f}s  {text[:58]}…')
    print(f'\n  narration total: {total:.0f}s of a 180s budget')
    return 0


if __name__ == '__main__':
    sys.exit(main())
