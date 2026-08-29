"""PlacesTool — real, named places from OpenStreetMap and Wikipedia.

This is the tool that replaced the invented hotel list. Every hotel it returns
is a real establishment with real coordinates that a person can walk into.
No API key required.

Sources:
  Nominatim  — geocode a destination to a bounding point        (ODbL)
  Overpass   — hotels/resorts/guesthouses tagged in OSM         (ODbL)
  Wikipedia  — human description of the area                    (CC BY-SA)

What it deliberately does NOT provide: nightly rates or availability. OSM has
no prices. Rates come from HotelRatesTool, and when that is unconfigured the
agent says so rather than inventing a number.

Capabilities: find_hotels, geocode_place, describe_area
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from .base import ToolBase, ToolCapability, ToolError, ToolResult, ToolStatus
from .provenance import Provenance, SourceStatus, stamp

logger = logging.getLogger(__name__)

# OSM usage policy requires a descriptive UA identifying the application.
USER_AGENT = 'Waypoint/1.0 (travel planning agent; +https://github.com/waypoint)'

OSM_ATTRIBUTION = '© OpenStreetMap contributors (ODbL)'
WIKI_ATTRIBUTION = 'Text from Wikipedia (CC BY-SA 4.0)'

# Overpass mirrors, tried in order — the main instance rate-limits aggressively.
OVERPASS_ENDPOINTS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
    'https://overpass.osm.jp/api/interpreter',
]

# How OSM marks an airport people actually fly from. A major hub carries
# aerodrome=international; Seletar carries it too but is tagged regional, and
# an air base carries military tags — hence tiers rather than a single flag.
#
# Tier beats distance outright. Weighting distance by tier was not enough: from
# north-east Singapore, Seletar at 1.4 km still outranked Changi at 15 km, and
# Seletar has no scheduled passenger service. Someone booking a flight wants
# the international airport even when a smaller field is closer.
AIRPORT_TIER_INTERNATIONAL = 3

NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'
WIKI_SUMMARY_URL = 'https://en.wikipedia.org/api/rest_v1/page/summary/{title}'

# Airport codes the agent may pass in place of a city name.
IATA_TO_PLACE = {
    'DPS': 'Bali, Indonesia',       'SIN': 'Singapore',
    'BKK': 'Bangkok, Thailand',     'KUL': 'Kuala Lumpur, Malaysia',
    'NRT': 'Tokyo, Japan',          'HND': 'Tokyo, Japan',
    'ICN': 'Seoul, South Korea',    'HKG': 'Hong Kong',
    'PEN': 'Penang, Malaysia',      'HKT': 'Phuket, Thailand',
    'CNX': 'Chiang Mai, Thailand',  'CGK': 'Jakarta, Indonesia',
    'SGN': 'Ho Chi Minh City, Vietnam', 'HAN': 'Hanoi, Vietnam',
    'MNL': 'Manila, Philippines',   'CMB': 'Colombo, Sri Lanka',
    'REP': 'Siem Reap, Cambodia',   'JFK': 'New York City, USA',
    'LAX': 'Los Angeles, USA',      'LHR': 'London, UK',
    'CDG': 'Paris, France',         'DXB': 'Dubai, UAE',
    'SYD': 'Sydney, Australia',     'MEL': 'Melbourne, Australia',
}

# OSM star ratings are sparse; these tags stand in for quality signals.
LUXURY_HINTS = ('resort', 'spa', 'villa', 'suites')


def _normalize_name(name: str) -> str:
    """Strip the words that differ between listings of the same hotel."""
    import re
    noise = ('hotel', 'resort', 'villa', 'villas', 'spa', 'the', 'by', 'and',
             'suites', 'house', 'bali', 'ubud', 'boutique', 'a', 'at')
    words = re.sub(r'[^a-z0-9 ]', ' ', name.lower()).split()
    kept = [w for w in words if w not in noise]
    return ' '.join(kept or words)


def _name_similarity(a: str, b: str) -> float:
    """Token overlap, biased toward the shorter name being contained."""
    from difflib import SequenceMatcher
    if not a or not b:
        return 0.0
    ta, tb = set(a.split()), set(b.split())
    overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
    return max(overlap, SequenceMatcher(None, a, b).ratio())


class _TTLCache:
    """Small thread-safe cache — OSM asks that we not re-query needlessly."""

    def __init__(self, ttl: int = 3600):
        self._ttl = ttl
        self._data: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            hit = self._data.get(key)
            if hit and time.time() - hit[0] < self._ttl:
                return hit[1]
            self._data.pop(key, None)
            return None

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = (time.time(), value)


class PlacesTool(ToolBase):
    """Real places from OpenStreetMap. No key, no invented data."""

    def __init__(self, timeout: int = 30):
        self._timeout = timeout
        self._cache = _TTLCache(ttl=3600)
        self._session = requests.Session()
        self._session.headers.update({'User-Agent': USER_AGENT})

    @property
    def name(self) -> str:
        return 'places'

    @property
    def description(self) -> str:
        return 'Find real, named hotels and describe areas using OpenStreetMap and Wikipedia'

    @property
    def capabilities(self) -> List[ToolCapability]:
        return [
            ToolCapability(
                name='find_hotels',
                description=(
                    'Find REAL hotels that exist in a destination, with coordinates, '
                    'star rating, website and address. Returns no prices — OSM has none.'
                ),
                parameters={
                    'destination': 'City name or IATA code, e.g. "Ubud, Bali" or "DPS"',
                    'radius_m': 'Search radius in metres (default 6000, max 25000)',
                    'limit': 'Max hotels to return (default 20)',
                    'min_stars': 'Only return hotels tagged at least this many stars (optional)',
                },
                returns='list[Hotel]',
                required=['destination'],
            ),
            ToolCapability(
                name='nearest_airports',
                description=(
                    'Find the real airports nearest a set of coordinates, with IATA '
                    'codes and distances. Use this to work out where the traveller is '
                    'actually flying from instead of assuming a hub.'
                ),
                parameters={
                    'lat': 'Latitude',
                    'lon': 'Longitude',
                    'radius_km': 'How far to look (default 250, max 600)',
                    'limit': 'Max airports to return (default 5)',
                },
                returns='list[Airport]',
                required=['lat', 'lon'],
            ),
            ToolCapability(
                name='match_hotel',
                description=(
                    'Look up a hotel you already know by name and coordinates in '
                    'OpenStreetMap to recover its OFFICIAL WEBSITE, phone and address. '
                    'Use this on a hotel from hotel_rates before capturing a website '
                    'screenshot, since rate results do not carry the official site.'
                ),
                parameters={
                    'name': 'Hotel name as returned by another tool',
                    'lat': 'Latitude of the hotel',
                    'lon': 'Longitude of the hotel',
                },
                returns='HotelMatch',
                required=['name', 'lat', 'lon'],
            ),
            ToolCapability(
                name='geocode_place',
                description='Resolve a place name to real coordinates and a display name',
                parameters={'query': 'Place name to look up'},
                returns='Coordinates',
                required=['query'],
            ),
            ToolCapability(
                name='describe_area',
                description='Get a factual Wikipedia description of a neighbourhood or town',
                parameters={'place': 'Place name, e.g. "Ubud"'},
                returns='AreaDescription',
                required=['place'],
            ),
        ]

    def execute(self, capability: str, params: Dict[str, Any]) -> ToolResult:
        if capability == 'find_hotels':
            return self.find_hotels(params)
        if capability == 'nearest_airports':
            return self.nearest_airports(params)
        if capability == 'match_hotel':
            return self.match_hotel(params)
        if capability == 'geocode_place':
            return self.geocode_place(params)
        if capability == 'describe_area':
            return self.describe_area(params)
        raise ToolError(f"Unknown capability: {capability}",
                        tool_name=self.name, capability=capability)

    # ── geocoding ────────────────────────────────────────────────

    def _resolve_query(self, destination: str) -> str:
        """Expand an IATA code into a searchable place name."""
        key = (destination or '').strip()
        return IATA_TO_PLACE.get(key.upper(), key)

    def geocode_place(self, params: Dict[str, Any]) -> ToolResult:
        query = self._resolve_query(params.get('query') or params.get('destination', ''))
        if not query:
            return ToolResult(status=ToolStatus.ERROR, message='query is required',
                              error='Missing query')

        cached = self._cache.get(f'geo:{query.lower()}')
        if cached:
            prov = Provenance('nominatim', SourceStatus.CACHED, url=NOMINATIM_URL,
                              license='ODbL', attribution=OSM_ATTRIBUTION)
            return ToolResult(status=ToolStatus.SUCCESS, data=stamp(dict(cached), prov),
                              message=f"{cached['display_name']} (cached)")

        try:
            resp = self._session.get(
                NOMINATIM_URL,
                params={'q': query, 'format': 'json', 'limit': 1, 'addressdetails': 1},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            prov = Provenance('nominatim', SourceStatus.FAILED, url=NOMINATIM_URL,
                              detail=f'{type(exc).__name__}: {exc}')
            return ToolResult(status=ToolStatus.ERROR, data={'provenance': prov.to_dict()},
                              message=f'Could not reach OpenStreetMap geocoder: {exc}',
                              error=str(exc))

        if resp.status_code != 200:
            prov = Provenance('nominatim', SourceStatus.FAILED, url=NOMINATIM_URL,
                              detail=f'HTTP {resp.status_code}')
            return ToolResult(status=ToolStatus.ERROR, data={'provenance': prov.to_dict()},
                              message=f'Geocoder returned HTTP {resp.status_code}',
                              error=f'HTTP {resp.status_code}')

        hits = resp.json()
        if not hits:
            prov = Provenance('nominatim', SourceStatus.UNAVAILABLE, url=NOMINATIM_URL,
                              detail=f'no match for {query!r}')
            return ToolResult(status=ToolStatus.NO_RESULTS,
                              data={'provenance': prov.to_dict()},
                              message=f"OpenStreetMap has no place called {query!r}")

        hit = hits[0]
        place = {
            'query': query,
            'display_name': hit.get('display_name', query),
            'lat': float(hit['lat']),
            'lon': float(hit['lon']),
            'osm_type': hit.get('osm_type', ''),
            'osm_id': hit.get('osm_id', ''),
            'place_class': hit.get('class', ''),
            'country': (hit.get('address') or {}).get('country', ''),
        }
        self._cache.set(f'geo:{query.lower()}', place)
        prov = Provenance('nominatim', SourceStatus.LIVE, url=NOMINATIM_URL,
                          license='ODbL', attribution=OSM_ATTRIBUTION)
        return ToolResult(status=ToolStatus.SUCCESS, data=stamp(place, prov),
                          message=f"{place['display_name']} @ {place['lat']:.4f},{place['lon']:.4f}")

    # ── hotels ───────────────────────────────────────────────────

    def find_hotels(self, params: Dict[str, Any]) -> ToolResult:
        destination = params.get('destination', '')
        radius = min(int(params.get('radius_m', 6000) or 6000), 25000)
        limit = int(params.get('limit', 20) or 20)
        min_stars = int(params.get('min_stars', 0) or 0)

        geo = self.geocode_place({'query': destination})
        if not geo.is_success():
            return ToolResult(status=geo.status, data=geo.data,
                              message=f"Could not locate {destination!r}: {geo.message}",
                              error=geo.error)

        lat, lon = geo.data['lat'], geo.data['lon']
        cache_key = f'hotels:{lat:.3f},{lon:.3f}:{radius}'
        elements = self._cache.get(cache_key)
        cached = elements is not None

        if not cached:
            elements, err = self._overpass_hotels(lat, lon, radius)
            if elements is None:
                prov = Provenance('osm', SourceStatus.FAILED, detail=err or 'unknown error')
                return ToolResult(
                    status=ToolStatus.ERROR, data={'provenance': prov.to_dict()},
                    message=(f"Could not reach OpenStreetMap for hotels near {destination}. "
                             f"I will not invent hotel listings — {err}"),
                    error=err,
                )
            self._cache.set(cache_key, elements)

        prov = Provenance(
            'osm', SourceStatus.CACHED if cached else SourceStatus.LIVE,
            url=OVERPASS_ENDPOINTS[0], license='ODbL', attribution=OSM_ATTRIBUTION,
            detail=f'tourism=hotel|resort|guest_house within {radius}m',
        )

        hotels = []
        for el in elements:
            hotel = self._normalize(el, lat, lon, prov)
            if hotel and (not min_stars or (hotel['stars'] or 0) >= min_stars):
                hotels.append(hotel)

        # Named, well-described places first — an unnamed OSM node is useless to a traveller.
        hotels.sort(key=lambda h: (-h['completeness'], h['distance_km']))
        hotels = hotels[:limit]

        if not hotels:
            return ToolResult(
                status=ToolStatus.NO_RESULTS,
                data={'destination': destination, 'hotels': [], 'provenance': prov.to_dict()},
                message=f'OpenStreetMap lists no hotels within {radius}m of {destination}',
            )

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                'destination': destination,
                'center': {'lat': lat, 'lon': lon,
                           'display_name': geo.data['display_name']},
                'hotels': hotels,
                'count': len(hotels),
                'radius_m': radius,
                'provenance': prov.to_dict(),
                'has_prices': False,
                'note': 'OpenStreetMap has no rates. These are real hotels without prices.',
            },
            message=f'Found {len(hotels)} real hotels near {geo.data["display_name"]}',
        )

    def _overpass(self, query: str, timeout: Optional[int] = None):
        """POST a query to Overpass, trying each mirror. Returns (elements, error)."""
        last_err = ''
        budget = timeout if timeout is not None else self._timeout + 20
        for endpoint in OVERPASS_ENDPOINTS:
            try:
                resp = self._session.post(
                    endpoint, data=query.encode('utf-8'),
                    headers={'Content-Type': 'text/plain; charset=utf-8'},
                    timeout=budget,
                )
                if resp.status_code == 200:
                    return resp.json().get('elements', []), None
                last_err = f'{endpoint} HTTP {resp.status_code}'
                logger.warning('Overpass %s', last_err)
            except requests.RequestException as exc:
                last_err = f'{endpoint} {type(exc).__name__}: {exc}'
                logger.warning('Overpass %s', last_err)
        return None, last_err

    def _overpass_hotels(self, lat: float, lon: float, radius: int):
        """Query Overpass for lodging around a point. Returns (elements, error)."""
        query = (
            f'[out:json][timeout:25];'
            f'('
            f'node["tourism"~"^(hotel|resort|guest_house|hostel)$"](around:{radius},{lat},{lon});'
            f'way["tourism"~"^(hotel|resort|guest_house|hostel)$"](around:{radius},{lat},{lon});'
            f');'
            f'out center tags 200;'
        )
        return self._overpass(query)

    @staticmethod
    def _normalize(el: Dict[str, Any], clat: float, clon: float,
                   prov: Provenance) -> Optional[Dict[str, Any]]:
        tags = el.get('tags', {}) or {}
        name = tags.get('name') or tags.get('name:en')
        if not name:
            return None  # An unnamed node cannot be shown to a traveller.

        # Ways carry their position under 'center'.
        lat = el.get('lat') or (el.get('center') or {}).get('lat')
        lon = el.get('lon') or (el.get('center') or {}).get('lon')
        if lat is None or lon is None:
            return None

        try:
            stars = int(str(tags.get('stars', '')).strip()[0])
        except (ValueError, IndexError):
            stars = None

        website = (tags.get('website') or tags.get('contact:website')
                   or tags.get('url') or '')
        if website and not website.startswith(('http://', 'https://')):
            website = 'https://' + website

        street = ' '.join(filter(None, [tags.get('addr:housenumber'), tags.get('addr:street')]))
        address = ', '.join(filter(None, [street, tags.get('addr:suburb'),
                                          tags.get('addr:city'), tags.get('addr:postcode')]))

        amenities = []
        for tag, label in (('internet_access', 'Internet'), ('swimming_pool', 'Swimming pool'),
                           ('air_conditioning', 'Air conditioning'), ('wheelchair', 'Accessible'),
                           ('restaurant', 'Restaurant'), ('spa', 'Spa')):
            val = tags.get(tag)
            if val and val not in ('no', 'none'):
                amenities.append(label)
        if tags.get('tourism') == 'resort' or any(h in name.lower() for h in LUXURY_HINTS):
            amenities.append('Resort grounds')

        # Straight-line distance from the search centre (equirectangular, fine at city scale).
        import math
        dx = math.radians(lon - clon) * math.cos(math.radians((lat + clat) / 2)) * 6371
        dy = math.radians(lat - clat) * 6371
        distance_km = round(math.hypot(dx, dy), 2)

        # How much OSM actually knows about this place — drives ranking.
        completeness = sum(bool(x) for x in (website, address, stars, tags.get('phone'),
                                             tags.get('tourism') == 'hotel', amenities))

        record = {
            'hotel_id': f"osm_{el.get('type', 'node')}_{el.get('id')}",
            'name': name,
            'kind': tags.get('tourism', 'hotel'),
            'stars': stars,
            'lat': lat,
            'lon': lon,
            'distance_km': distance_km,
            'website': website,
            'phone': tags.get('phone') or tags.get('contact:phone', ''),
            'address': address,
            'area': tags.get('addr:suburb') or tags.get('addr:city', ''),
            'amenities': amenities,
            'osm_url': f"https://www.openstreetmap.org/{el.get('type', 'node')}/{el.get('id')}",
            'completeness': completeness,
            # Explicitly absent — never guessed. Filled in by HotelRatesTool if configured.
            'price_per_night': None,
            'total_price': None,
            'currency': None,
            'rate_provenance': None,
            'image_url': None,
        }
        return stamp(record, prov)

    # ── airports ─────────────────────────────────────────────────

    def nearest_airports(self, params: Dict[str, Any]) -> ToolResult:
        """Real airports near a point, from OpenStreetMap.

        This replaced a hardcoded ten-airport table that silently returned
        nothing outside a handful of hubs, which is how the agent ended up
        assuming everyone departs from Kuala Lumpur.
        """
        lat, lon = params.get('lat'), params.get('lon')
        if lat is None or lon is None:
            return ToolResult(status=ToolStatus.ERROR,
                              message='lat and lon are required', error='Missing coordinates')
        lat, lon = float(lat), float(lon)
        radius = min(int(params.get('radius_km', 250) or 250), 600)
        limit = int(params.get('limit', 5) or 5)

        cache_key = f'apt:{lat:.2f},{lon:.2f}:{radius}'
        elements = self._cache.get(cache_key)
        cached = elements is not None

        if not cached:
            query = (
                f'[out:json][timeout:25];'
                f'('
                f'node["aeroway"="aerodrome"]["iata"](around:{radius * 1000},{lat},{lon});'
                f'way["aeroway"="aerodrome"]["iata"](around:{radius * 1000},{lat},{lon});'
                f'relation["aeroway"="aerodrome"]["iata"](around:{radius * 1000},{lat},{lon});'
                f');'
                f'out center tags 80;'
            )
            # Short timeout: this sits on the critical path of every search, and
            # Overpass routinely takes over a minute when it is busy.
            elements, err = self._overpass(query, timeout=20)
            if elements is None:
                return self._airports_from_reference(lat, lon, radius, limit, err)
            self._cache.set(cache_key, elements)

        prov = Provenance('osm', SourceStatus.CACHED if cached else SourceStatus.LIVE,
                          license='ODbL', attribution=OSM_ATTRIBUTION,
                          detail=f'aeroway=aerodrome with an IATA code within {radius}km')

        import math
        airports = []
        for el in elements:
            tags = el.get('tags', {}) or {}
            iata = (tags.get('iata') or '').strip().upper()
            # Some OSM nodes carry several codes in one tag; take the first valid one.
            iata = iata.split(';')[0].strip()
            if len(iata) != 3 or not iata.isalpha():
                continue
            alat = el.get('lat') or (el.get('center') or {}).get('lat')
            alon = el.get('lon') or (el.get('center') or {}).get('lon')
            if alat is None or alon is None:
                continue
            dx = math.radians(alon - lon) * math.cos(math.radians((alat + lat) / 2)) * 6371
            dy = math.radians(alat - lat) * 6371
            kind = (tags.get('aerodrome:type') or '').lower()
            # An air base is not somewhere anyone buys a ticket from.
            if kind == 'military' or tags.get('military') or tags.get('access') == 'private':
                continue

            is_intl = tags.get('aerodrome') == 'international' or kind == 'international'
            if kind == 'international':
                tier = 3
            elif is_intl and kind != 'regional':
                tier = 3
            elif kind == 'regional' or tags.get('icao'):
                tier = 2
            else:
                tier = 1

            airports.append({
                'iata': iata,
                'icao': tags.get('icao', ''),
                'name': tags.get('name') or tags.get('name:en') or iata,
                'city': tags.get('addr:city') or tags.get('is_in:city') or '',
                'lat': alat,
                'lon': alon,
                'distance_km': round(math.hypot(dx, dy), 1),
                'international': is_intl,
                'tier': tier,
            })

        # Highest tier first, then nearest within that tier. A regional field
        # only surfaces when nothing international is in range.
        airports.sort(key=lambda a: (-a['tier'], a['distance_km']))
        seen, unique = set(), []
        for a in airports:
            if a['iata'] not in seen:
                seen.add(a['iata'])
                unique.append(a)
        unique = unique[:limit]

        if not unique:
            # OSM answered but had nothing usable; the bundled list may still.
            fallback = self._airports_from_reference(lat, lon, radius, limit,
                                                     'OpenStreetMap listed no usable airport')
            if fallback.is_success():
                return fallback
            prov_none = Provenance('osm', SourceStatus.UNAVAILABLE,
                                   detail=f'no IATA airport within {radius}km')
            return ToolResult(status=ToolStatus.NO_RESULTS,
                              data={'airports': [], 'provenance': prov_none.to_dict()},
                              message=f'No airport with an IATA code within {radius}km')

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={'airports': unique, 'count': len(unique),
                  'origin': {'lat': lat, 'lon': lon},
                  'provenance': prov.to_dict()},
            message=(f"Nearest airport is {unique[0]['iata']} ({unique[0]['name']}), "
                     f"{unique[0]['distance_km']}km away"),
        )

    @staticmethod
    def _airports_from_reference(lat: float, lon: float, radius: int, limit: int,
                                 why: str) -> ToolResult:
        """Fall back to the bundled airport list when Overpass will not answer.

        These are real airports from a local reference, not live data, so the
        provenance says so rather than implying a lookup that did not happen.
        """
        from .airports import nearest

        found = nearest(lat, lon, radius_km=max(radius, 300), limit=limit)
        if not found:
            prov = Provenance('osm', SourceStatus.FAILED, detail=why)
            return ToolResult(
                status=ToolStatus.ERROR,
                data={'airports': [], 'provenance': prov.to_dict()},
                message=(f'Could not find an airport near {lat:.3f},{lon:.3f}: {why}'),
                error=why)

        prov = Provenance('builtin', SourceStatus.CACHED,
                          detail=f'bundled airport reference ({why})',
                          attribution='Major airport reference bundled with Waypoint')
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={'airports': found, 'count': len(found),
                  'origin': {'lat': lat, 'lon': lon},
                  'fallback': True, 'provenance': prov.to_dict()},
            message=(f"Nearest airport is {found[0]['iata']} ({found[0]['name']}), "
                     f"{found[0]['distance_km']}km away — from the bundled list, "
                     f"because the live lookup was unavailable"),
        )

    # ── matching a known hotel back to OSM ───────────────────────

    def match_hotel(self, params: Dict[str, Any]) -> ToolResult:
        """Find the OSM record for a hotel we already know, to get its website.

        Booking.com results carry no official site. OSM often does, which is
        what makes a real screenshot of the hotel's own page possible.
        """
        name = (params.get('name') or '').strip()
        lat, lon = params.get('lat'), params.get('lon')
        if not name or lat is None or lon is None:
            return ToolResult(status=ToolStatus.ERROR,
                              message='name, lat and lon are all required',
                              error='Missing parameters')

        lat, lon = float(lat), float(lon)
        # Hotels sit within a few hundred metres of their listed coordinates.
        elements, err = self._overpass_hotels(lat, lon, 1200)
        if elements is None:
            prov = Provenance('osm', SourceStatus.FAILED, detail=err or 'unknown error')
            return ToolResult(status=ToolStatus.ERROR, data={'provenance': prov.to_dict()},
                              message=f'Could not reach OpenStreetMap to match {name!r}: {err}',
                              error=err)

        prov = Provenance('osm', SourceStatus.LIVE, license='ODbL',
                          attribution=OSM_ATTRIBUTION,
                          detail=f'matched {name!r} within 1200m')

        candidates = [c for c in (self._normalize(e, lat, lon, prov) for e in elements) if c]
        target = _normalize_name(name)
        best, best_score = None, 0.0
        for cand in candidates:
            score = _name_similarity(target, _normalize_name(cand['name']))
            if score > best_score:
                best, best_score = cand, score

        # Below this the 'match' is really a different hotel next door.
        if not best or best_score < 0.55:
            prov_none = Provenance('osm', SourceStatus.UNAVAILABLE,
                                   detail=f'no OSM hotel within 1200m resembling {name!r}')
            return ToolResult(
                status=ToolStatus.NO_RESULTS,
                data={'query': name, 'matched': None, 'provenance': prov_none.to_dict()},
                message=(f'OpenStreetMap has no confident match for {name!r}. '
                         f'No official website available — capture a map view instead.'),
            )

        best['match_confidence'] = round(best_score, 2)
        best['matched_query'] = name
        return ToolResult(
            status=ToolStatus.SUCCESS, data=best,
            message=(f"Matched {name!r} to OSM '{best['name']}' "
                     f"({best_score:.0%} confident)" +
                     (f" — website {best['website']}" if best['website'] else ' — no website on file')),
        )

    # ── area description ─────────────────────────────────────────

    def describe_area(self, params: Dict[str, Any]) -> ToolResult:
        place = params.get('place') or params.get('destination', '')
        if not place:
            return ToolResult(status=ToolStatus.ERROR, message='place is required',
                              error='Missing place')

        title = self._resolve_query(place).split(',')[0].strip().replace(' ', '_')
        url = WIKI_SUMMARY_URL.format(title=title)
        try:
            resp = self._session.get(url, timeout=self._timeout)
        except requests.RequestException as exc:
            prov = Provenance('wikipedia', SourceStatus.FAILED, url=url, detail=str(exc))
            return ToolResult(status=ToolStatus.ERROR, data={'provenance': prov.to_dict()},
                              message=f'Could not reach Wikipedia: {exc}', error=str(exc))

        if resp.status_code != 200:
            prov = Provenance('wikipedia', SourceStatus.UNAVAILABLE, url=url,
                              detail=f'HTTP {resp.status_code}')
            return ToolResult(status=ToolStatus.NO_RESULTS, data={'provenance': prov.to_dict()},
                              message=f'Wikipedia has no article for {place!r}')

        body = resp.json()
        prov = Provenance('wikipedia', SourceStatus.LIVE, url=url,
                          license='CC BY-SA 4.0', attribution=WIKI_ATTRIBUTION)
        record = {
            'place': place,
            'title': body.get('title', place),
            'summary': body.get('extract', ''),
            'image_url': (body.get('thumbnail') or {}).get('source', ''),
            'wikipedia_url': (body.get('content_urls', {}).get('desktop', {}) or {}).get('page', ''),
            'coordinates': body.get('coordinates', {}),
        }
        return ToolResult(status=ToolStatus.SUCCESS, data=stamp(record, prov),
                          message=f"Wikipedia: {record['title']}")
