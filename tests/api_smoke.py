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
        # NB: `environment` only has a `use` subcommand in CLI 0.3.12 — there
        # is no way to query the current environment, so we do not check it.
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
    print("\n── RapidAPI / Booking.com ────────────────────────────────")
    key = os.getenv('RAPIDAPI_KEY', '')
    if not key:
        record('rapidapi key present', False, 'unset'); return
    record('rapidapi key present', True, f"{key[:8]}…{key[-4:]}")

    host = 'booking-com15.p.rapidapi.com'
    H = {'x-rapidapi-key': key, 'x-rapidapi-host': host}

    (r, ms, err) = timed(lambda: requests.get(
        f'https://{host}/api/v1/hotels/searchDestination',
        params={'query': 'Bali'}, headers=H, timeout=25))
    if err:
        record('booking15 searchDestination', False, type(err).__name__, ms, str(err)[:160]); return
    ok = r.status_code == 200
    hint = '' if ok else 'subscribe this key to booking-com15 on rapidapi.com (free BASIC plan)'
    dest = (r.json().get('data') or [{}]) if ok else [{}]
    record('booking15 searchDestination', ok, f"HTTP {r.status_code}", ms,
           f"{len(dest)} destinations | {dest[0].get('label','')}" if ok else f"{hint} | {r.text[:120]}")
    if not ok:
        return

    city = next((d for d in dest if d.get('search_type') == 'city'), dest[0])
    (r, ms, err) = timed(lambda: requests.get(
        f'https://{host}/api/v1/hotels/searchHotels', headers=H, timeout=30,
        params={'dest_id': city.get('dest_id'), 'search_type': city.get('search_type'),
                'arrival_date': DEPART, 'departure_date': RETURN, 'adults': '2',
                'room_qty': '1', 'page_number': '1', 'currency_code': 'USD',
                'languagecode': 'en-us', 'units': 'metric'}))
    if err:
        record('booking15 searchHotels', False, type(err).__name__, ms, str(err)[:160]); return
    hotels = ((r.json().get('data') or {}).get('hotels') or []) if r.status_code == 200 else []
    priced = [h for h in hotels
              if ((h.get('property') or {}).get('priceBreakdown') or {}).get('grossPrice')]
    withpix = [h for h in hotels if (h.get('property') or {}).get('photoUrls')]
    record('booking15 searchHotels', bool(priced), f"HTTP {r.status_code} hotels={len(hotels)}", ms,
           f"{len(priced)} priced, {len(withpix)} with real photos")


# ── The authentic-data stack this project now runs on ────────────────
def test_stack():
    print("\n── Waypoint tool stack (live) ────────────────────────────")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from src.tools import tool_registry
    from src.tools.places_tool import PlacesTool
    from src.tools.imagery_tool import ImageryTool

    record('registry loads', True,
           f"{len(tool_registry.list_tools())} tools, "
           f"{len(tool_registry.all_capabilities())} capabilities")

    places = PlacesTool()
    (res, ms, err) = timed(lambda: places.find_hotels(
        {'destination': 'Ubud, Bali', 'radius_m': 5000, 'limit': 8}))
    if err:
        record('places.find_hotels (OSM)', False, type(err).__name__, ms, str(err)[:160])
    else:
        hotels = (res.data or {}).get('hotels', [])
        named = [h['name'] for h in hotels[:3]]
        record('places.find_hotels (OSM)', res.is_success(),
               f"{len(hotels)} real hotels", ms, ', '.join(named))
        # The contract that matters: no invented prices.
        no_prices = all(h.get('price_per_night') is None for h in hotels)
        record('  └ OSM hotels carry no fake price', no_prices,
               'all prices None' if no_prices else 'A PRICE WAS INVENTED')

    (res, ms, err) = timed(lambda: places.find_hotels({'destination': 'Zzqqxnowhere'}))
    good = (not err) and not res.is_success() and not (res.data or {}).get('hotels')
    record('bogus place returns nothing', good,
           res.status.value if not err else 'exception', ms,
           res.message[:120] if not err else str(err)[:120])

    imagery = ImageryTool()
    (res, ms, err) = timed(lambda: imagery.capture_hotel_view(
        {'name': 'Maya Ubud', 'website': 'http://www.mayaubud.com',
         'lat': -8.5131489, 'lon': 115.2779248}))
    if err:
        record('imagery website screenshot', False, type(err).__name__, ms, str(err)[:160])
    else:
        record('imagery website screenshot', res.is_success(),
               f"mode={res.data.get('capture_mode')} {res.data.get('bytes', 0)}b", ms,
               res.data.get('image_url', ''))

    (res, ms, err) = timed(lambda: imagery.capture_hotel_view({'name': 'Nowhere Inn'}))
    refused = (not err) and not res.data.get('image_url')
    record('imagery refuses to fake', refused,
           'no image returned' if refused else 'RETURNED AN IMAGE IT SHOULD NOT HAVE',
           ms, res.message[:110] if not err else '')


# ── The running Flask app ────────────────────────────────────────────
def test_endpoints():
    print("\n── Flask endpoints ───────────────────────────────────────")
    base = os.getenv('WAYPOINT_URL', 'http://localhost:2000')
    checks = [
        ('GET /api/state', 'get', '/api/state', None),
        ('GET /api/tools', 'get', '/api/tools', None),
        ('GET /api/sources', 'get', '/api/sources', None),
        ('GET /api/flight-delays', 'get', '/api/flight-delays?airport=SIN', None),
        ('GET /api/tracker/summary', 'get', '/api/tracker/summary', None),
        ('POST /api/chat', 'post', '/api/chat', {'message': 'hello'}),
        ('POST /api/agent/plan', 'post', '/api/agent/plan',
         {'request': 'One night in Singapore on ' + DEPART + ', 1 adult, cheapest option'}),
    ]
    for label, verb, path, body in checks:
        fn = (lambda: requests.get(base + path, timeout=180)) if verb == 'get' else \
             (lambda: requests.post(base + path, json=body, timeout=180))
        (r, ms, err) = timed(fn)
        if err:
            record(label, False, type(err).__name__, ms,
                   'is the server running?  python run.py'); continue
        ok = r.status_code == 200
        detail = ''
        try:
            body_json = r.json()
            if isinstance(body_json, dict):
                if body_json.get('success') is False:
                    ok = False
                    detail = str(body_json.get('error'))[:140]
                elif 'tool_calls' in body_json:
                    detail = (f"{body_json['tool_calls']} tool calls, "
                              f"{len(body_json.get('packages', []))} packages, "
                              f"stopped={body_json.get('stopped')}")
        except ValueError:
            pass
        record(label, ok, f'HTTP {r.status_code}', ms, detail)


# ── ElevenLabs ───────────────────────────────────────────────────────
def test_elevenlabs():
    print("\n── ElevenLabs ────────────────────────────────────────────")
    key = os.getenv('ELEVENLABS_API_KEY', '')
    if not key:
        record('elevenlabs key present', False, 'unset'); return
    record('elevenlabs key present', True, f"{key[:8]}…{key[-4:]}")

    # A TTS-scoped key cannot read /v1/user. That is fine — only TTS is used —
    # so a 401 here is reported as a note, not a failure.
    (r, ms, err) = timed(lambda: requests.get('https://api.elevenlabs.io/v1/user',
                                              headers={'xi-api-key': key}, timeout=20))
    if err:
        record('elevenlabs /v1/user', None, type(err).__name__, ms, str(err)[:160])
    else:
        record('elevenlabs /v1/user', True if r.status_code == 200 else None,
               f"HTTP {r.status_code}", ms,
               'key is TTS-scoped; user_read not granted (expected)'
               if r.status_code == 401 else r.text[:160])

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
          'rapidapi': test_rapidapi, 'elevenlabs': test_elevenlabs,
          'alternatives': test_alternatives, 'stack': test_stack,
          'endpoints': test_endpoints}

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
