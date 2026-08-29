#!/usr/bin/env python3
"""API smoke tests — hits every external dependency and reports pass/fail.

Usage:
    venv/bin/python tests/api_smoke.py            # all
    venv/bin/python tests/api_smoke.py atlas openai
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

import requests

RESULTS = []
DEPART = (date.today() + timedelta(days=30)).isoformat()
RETURN = (date.today() + timedelta(days=34)).isoformat()
ATLAS_ENV = dict(os.environ, PATH=os.path.expanduser("~/.local/bin") + ":" + os.environ.get("PATH", ""))


def record(name, ok, detail, ms=0, note=''):
    RESULTS.append({'name': name, 'ok': ok, 'detail': detail, 'ms': int(ms), 'note': note})
    icon = '✅' if ok is True else ('⚠️ ' if ok is None else '❌')
    print(f"{icon} {name:<38} {int(ms):>6}ms  {detail}")
    if note:
        print(f"    ↳ {note}")


def timed(fn):
    t0 = time.time()
    try:
        return fn(), (time.time() - t0) * 1000, None
    except Exception as e:
        return None, (time.time() - t0) * 1000, e


# ── Atlas CLI ────────────────────────────────────────────────────────
def atlas(*args, timeout=90):
    p = subprocess.run(['atlas-flight', *args, '--json'], capture_output=True,
                       text=True, timeout=timeout, env=ATLAS_ENV)
    out = (p.stdout or p.stderr).strip()
    try:
        return p.returncode, json.loads(out)
    except json.JSONDecodeError:
        return p.returncode, {'_raw': out[:400]}


def test_atlas():
    print("\n── Atlas CLI ─────────────────────────────────────────────")
    for label, args in [
        ('atlas doctor', ['doctor']),
        ('atlas environment show', ['environment', 'show']),
        ('atlas auth status', ['auth', 'status']),
    ]:
        (res, ms, err) = timed(lambda a=args: atlas(*a))
        if err:
            record(label, False, type(err).__name__, ms, str(err)[:160]); continue
        rc, data = res
        record(label, rc == 0, f"rc={rc}", ms, json.dumps(data)[:200])

    def search():
        return atlas('search', '--origin', 'KUL', '--destination', 'SIN',
                     '--depart', DEPART, '--adults', '1')
    (res, ms, err) = timed(search)
    if err:
        record('atlas search KUL→SIN', False, type(err).__name__, ms, str(err)[:160])
        return None
    rc, data = res
    offers = data.get('offers') or data.get('data', {}).get('offers') or []
    ok = rc == 0 and len(offers) > 0
    record('atlas search KUL→SIN', ok, f"rc={rc} offers={len(offers)}", ms,
           json.dumps(offers[0])[:240] if offers else json.dumps(data)[:240])
    if not offers:
        return None
    offer_id = offers[0].get('offer_id') or offers[0].get('id')

    (res, ms, err) = timed(lambda: atlas('offer', 'verify', '--offer-id', offer_id))
    if err:
        record('atlas offer verify', False, type(err).__name__, ms, str(err)[:160])
    else:
        rc, data = res
        record('atlas offer verify', rc == 0, f"rc={rc} offer={offer_id[:20]}", ms, json.dumps(data)[:200])
    return offer_id


# ── OpenAI ───────────────────────────────────────────────────────────
def test_openai():
    print("\n── OpenAI ────────────────────────────────────────────────")
    key = os.getenv('OPENAI_API_KEY', '')
    if not key:
        record('openai key present', False, 'OPENAI_API_KEY unset'); return
    record('openai key present', True, f"{key[:8]}…{key[-4:]} ({len(key)} chars)")

    import openai
    client = openai.OpenAI(api_key=key)

    def chat():
        return client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{'role': 'user', 'content': 'Reply with the single word: ok'}],
            max_tokens=5)
    (r, ms, err) = timed(chat)
    if err:
        record('openai chat gpt-4o-mini', False, type(err).__name__, ms, str(err)[:200])
    else:
        record('openai chat gpt-4o-mini', True,
               f"{r.choices[0].message.content.strip()!r} tok={r.usage.total_tokens}", ms)

    def jsonmode():
        return client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{'role': 'system', 'content': 'Return JSON only.'},
                      {'role': 'user', 'content': 'Give {"city":"Bali","iata":"DPS"}'}],
            response_format={'type': 'json_object'}, max_tokens=50)
    (r, ms, err) = timed(jsonmode)
    if err:
        record('openai json mode', False, type(err).__name__, ms, str(err)[:200])
    else:
        record('openai json mode', True, r.choices[0].message.content.strip()[:80], ms)

    # Vision — used by /api/analyze-image
    def vision():
        px = ('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ'
              'AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
        return client.chat.completions.create(
            model='gpt-4o',
            messages=[{'role': 'user', 'content': [
                {'type': 'text', 'text': 'What color is this pixel? One word.'},
                {'type': 'image_url', 'image_url': {'url': px}}]}],
            max_tokens=10)
    (r, ms, err) = timed(vision)
    if err:
        record('openai vision gpt-4o', False, type(err).__name__, ms, str(err)[:200])
    else:
        record('openai vision gpt-4o', True, r.choices[0].message.content.strip()[:40], ms)


# ── AviationStack ────────────────────────────────────────────────────
def test_aviationstack():
    print("\n── AviationStack ─────────────────────────────────────────")
    key = os.getenv('AVIATIONSTACK_API_KEY', '')
    if not key:
        record('aviationstack key present', False, 'unset'); return
    record('aviationstack key present', True, f"{key[:6]}…{key[-4:]}")

    for scheme in ('https', 'http'):
        (r, ms, err) = timed(lambda s=scheme: requests.get(
            f'{s}://api.aviationstack.com/v1/flights',
            params={'access_key': key, 'dep_iata': 'SIN', 'limit': 3}, timeout=20))
        if err:
            record(f'aviationstack {scheme} /flights', False, type(err).__name__, ms, str(err)[:160]); continue
        try:
            body = r.json()
        except Exception:
            record(f'aviationstack {scheme} /flights', False, f"HTTP {r.status_code}", ms, r.text[:160]); continue
        if 'error' in body:
            record(f'aviationstack {scheme} /flights', False, f"HTTP {r.status_code}", ms,
                   json.dumps(body['error'])[:200])
        else:
            n = len(body.get('data', []))
            record(f'aviationstack {scheme} /flights', n > 0, f"HTTP {r.status_code} rows={n}", ms,
                   json.dumps(body.get('data', [{}])[0])[:200] if n else json.dumps(body)[:200])


# ── RapidAPI hotels ──────────────────────────────────────────────────
def test_rapidapi():
    print("\n── RapidAPI (hotels) ─────────────────────────────────────")
    key = os.getenv('RAPIDAPI_KEY', '')
    if not key:
        record('rapidapi key present', False, 'unset'); return
    record('rapidapi key present', True, f"{key[:8]}…{key[-4:]}")

    # What the code currently calls (hotels_tool.py)
    probes = [
        ('booking-com.p.rapidapi.com', '/v1/hotels/searchDestination', {'name': 'Bali'}, 'CURRENT CODE PATH'),
        ('booking-com.p.rapidapi.com', '/v1/hotels/locations', {'name': 'Bali', 'locale': 'en-gb'}, 'v1 correct path'),
        ('booking-com15.p.rapidapi.com', '/api/v1/hotels/searchDestination', {'query': 'Bali'}, 'v15 API'),
        ('booking-com18.p.rapidapi.com', '/stays/auto-complete', {'query': 'Bali'}, 'v18 API'),
    ]
    for host, path, params, note in probes:
        (r, ms, err) = timed(lambda h=host, p=path, q=params: requests.get(
            f'https://{h}{p}', params=q,
            headers={'X-RapidAPI-Key': key, 'X-RapidAPI-Host': h}, timeout=20))
        label = f'{host.split(".")[0]}{path}'
        if err:
            record(label, False, type(err).__name__, ms, f"{note} | {str(err)[:140]}"); continue
        ok = r.status_code == 200
        record(label, ok, f"HTTP {r.status_code}", ms, f"{note} | {r.text[:220]}")


# ── ElevenLabs ───────────────────────────────────────────────────────
def test_elevenlabs():
    print("\n── ElevenLabs ────────────────────────────────────────────")
    key = os.getenv('ELEVENLABS_API_KEY', '')
    if not key:
        record('elevenlabs key present', False, 'unset'); return
    record('elevenlabs key present', True, f"{key[:8]}…{key[-4:]}")

    (r, ms, err) = timed(lambda: requests.get('https://api.elevenlabs.io/v1/user',
                                              headers={'xi-api-key': key}, timeout=20))
    if err:
        record('elevenlabs /v1/user', False, type(err).__name__, ms, str(err)[:160])
    else:
        record('elevenlabs /v1/user', r.status_code == 200, f"HTTP {r.status_code}", ms, r.text[:200])

    (r, ms, err) = timed(lambda: requests.post(
        'https://api.elevenlabs.io/v1/text-to-speech/EXAVITQu4vr4xnSDxMaL',
        headers={'xi-api-key': key, 'Content-Type': 'application/json'},
        json={'text': 'Testing.', 'model_id': 'eleven_turbo_v2_5'}, timeout=30))
    if err:
        record('elevenlabs TTS', False, type(err).__name__, ms, str(err)[:160])
    else:
        record('elevenlabs TTS', r.status_code == 200,
               f"HTTP {r.status_code} bytes={len(r.content)}", ms,
               '' if r.status_code == 200 else r.text[:200])


# ── Free / no-key sources worth having ───────────────────────────────
def test_alternatives():
    print("\n── Candidate free sources (for authentic data) ───────────")
    (r, ms, err) = timed(lambda: requests.get(
        'https://nominatim.openstreetmap.org/search',
        params={'q': 'Ubud Village Hotel Bali', 'format': 'json', 'limit': 1},
        headers={'User-Agent': 'waypoint-smoke-test/1.0'}, timeout=20))
    if err:
        record('nominatim geocode', False, type(err).__name__, ms, str(err)[:160])
    else:
        d = r.json() if r.status_code == 200 else []
        record('nominatim geocode', bool(d), f"HTTP {r.status_code} hits={len(d)}", ms,
               json.dumps(d[0])[:200] if d else r.text[:160])

    q = '[out:json][timeout:20];node["tourism"="hotel"](around:3000,-8.5069,115.2625);out 5;'
    (r, ms, err) = timed(lambda: requests.post('https://overpass-api.de/api/interpreter',
                                               data={'data': q}, timeout=40))
    if err:
        record('overpass hotels near Ubud', False, type(err).__name__, ms, str(err)[:160])
    else:
        els = r.json().get('elements', []) if r.status_code == 200 else []
        record('overpass hotels near Ubud', bool(els), f"HTTP {r.status_code} hotels={len(els)}", ms,
               json.dumps([e.get('tags', {}).get('name') for e in els])[:200])

    (r, ms, err) = timed(lambda: requests.get('https://opensky-network.org/api/states/all',
                                              params={'lamin': 1.0, 'lomin': 103.0,
                                                      'lamax': 1.7, 'lomax': 104.3}, timeout=30))
    if err:
        record('opensky live aircraft', False, type(err).__name__, ms, str(err)[:160])
    else:
        st = (r.json().get('states') or []) if r.status_code == 200 else []
        record('opensky live aircraft', r.status_code == 200, f"HTTP {r.status_code} aircraft={len(st)}", ms)

    (r, ms, err) = timed(lambda: requests.get(
        'https://commons.wikimedia.org/w/api.php',
        params={'action': 'query', 'generator': 'geosearch', 'ggscoord': '-8.5069|115.2625',
                'ggsradius': 2000, 'ggslimit': 3, 'prop': 'imageinfo',
                'iiprop': 'url', 'iiurlwidth': 640, 'format': 'json'},
        headers={'User-Agent': 'waypoint-smoke-test/1.0'}, timeout=25))
    if err:
        record('wikimedia geo photos', False, type(err).__name__, ms, str(err)[:160])
    else:
        pages = (r.json().get('query', {}).get('pages', {}) if r.status_code == 200 else {})
        record('wikimedia geo photos', bool(pages), f"HTTP {r.status_code} pages={len(pages)}", ms)


SUITES = {'atlas': test_atlas, 'openai': test_openai, 'aviationstack': test_aviationstack,
          'rapidapi': test_rapidapi, 'elevenlabs': test_elevenlabs, 'alternatives': test_alternatives}

if __name__ == '__main__':
    want = sys.argv[1:] or list(SUITES)
    print(f"Waypoint API smoke test — depart={DEPART} return={RETURN}")
    for s in want:
        if s in SUITES:
            SUITES[s]()
        else:
            print(f"unknown suite: {s}")
    ok = sum(1 for r in RESULTS if r['ok'] is True)
    bad = [r for r in RESULTS if r['ok'] is False]
    print(f"\n{'='*66}\n{ok}/{len(RESULTS)} passed, {len(bad)} failed")
    for r in bad:
        print(f"  ❌ {r['name']}: {r['detail']}")
    json.dump(RESULTS, open(os.path.join(os.path.dirname(__file__), 'api_smoke_results.json'), 'w'), indent=2)
