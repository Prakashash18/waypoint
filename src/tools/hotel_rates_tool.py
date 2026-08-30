"""HotelRatesTool — real nightly rates, review scores and photographs.

Provider: Booking.com via RapidAPI (booking-com15).

This tool replaced the simulated hotel generator. The old code caught a
provider failure and returned invented hotels with random prices, which is
indistinguishable from real output to the caller. This tool instead returns an
error carrying provenance, so the agent can tell the user that rates are
unavailable rather than making one up.

Responses are cached on disk because the free RapidAPI tier is metered and a
trip search would otherwise burn quota re-asking the same question.

Capabilities: search_hotels, get_hotel_photos
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

from .base import ToolBase, ToolCapability, ToolError, ToolResult, ToolStatus
from .provenance import Provenance, SourceStatus, stamp

logger = logging.getLogger(__name__)

RAPIDAPI_HOST = 'booking-com15.p.rapidapi.com'
BASE = f'https://{RAPIDAPI_HOST}/api/v1'
# Overridable so a container keeps its cache on a mounted disk and does not
# re-spend the metered free tier after every restart.
CACHE_DIR = os.getenv(
    'WAYPOINT_CACHE_DIR',
    os.path.join(os.path.dirname(__file__), '..', '..', '.cache', 'hotel_rates'))
# The free RapidAPI tier is metered and small, so cache lifetimes are set per
# endpoint by how fast the answer actually changes — a city's id never moves,
# a hotel's photographs rarely do, and nightly rates drift slowly enough that a
# day is fine for planning.
CACHE_TTL = int(os.getenv('WAYPOINT_RATE_CACHE_TTL', 24 * 3600))
ENDPOINT_TTL = {
    '/hotels/searchDestination': int(os.getenv('WAYPOINT_DEST_CACHE_TTL', 30 * 86400)),
    '/hotels/getHotelPhotos': int(os.getenv('WAYPOINT_PHOTO_CACHE_TTL', 7 * 86400)),
}

# RapidAPI reports the real allowance on every response, and for the BASIC
# plan it is 50 requests a MONTH — not a day. A locally invented daily cap was
# meaningless against that, so the provider's own counter is the authority and
# this is only a secondary guard for a single runaway session.
# Generous by design: this is a guard against one runaway session, not a
# throttle. The provider's own allowance is the real limit.
DAILY_LIMIT = int(os.getenv('WAYPOINT_RAPIDAPI_DAILY_LIMIT', 400))

# Header names RapidAPI returns, lowercased.
QUOTA_HEADERS = ('x-ratelimit-requests-limit', 'x-ratelimit-requests-remaining',
                 'x-ratelimit-requests-reset')

# How long to trust a "nothing left" reading before probing again. A plan can
# be upgraded at any moment, and a stale zero would otherwise lock the app out
# of a provider that is perfectly willing to answer.
EXHAUSTED_RECHECK = int(os.getenv('WAYPOINT_QUOTA_RECHECK', 600))

ATTRIBUTION = 'Rates, review scores and photos from Booking.com via RapidAPI'

# Booking.com's own filter ids, verified against getFilter for this provider.
# Mapping them from plain needs keeps the agent (and the UI) out of the
# business of remembering numeric facility codes.
TRAVELLER_NEEDS = {
    'family':        (['facility::28'], 'family rooms'),
    'kids':          (['facility::28'], 'family rooms'),
    'wheelchair':    (['facility::185', 'accessible_room_facilities::134'],
                      'wheelchair-accessible property and unit'),
    'step_free':     (['accessible_room_facilities::131'], 'ground-floor unit'),
    'elderly':       (['accessible_room_facilities::132'], 'lift to upper floors'),
    'pool':          (['facility::433'], 'swimming pool'),
    'breakfast':     (['mealplan::breakfast_included'], 'breakfast included'),
    'well_reviewed': (['reviewscorebuckets::80'], 'guest score 8 or better'),
    'top_reviewed':  (['reviewscorebuckets::90'], 'guest score 9 or better'),
}


def filters_for(needs) -> tuple:
    """Turn plain needs into provider filter ids. Returns (ids, descriptions)."""
    ids, described, unknown = [], [], []
    for need in (needs or []):
        key = str(need).strip().lower().replace(' ', '_').replace('-', '_')
        match = TRAVELLER_NEEDS.get(key)
        if not match:
            unknown.append(need)
            continue
        for fid in match[0]:
            if fid not in ids:
                ids.append(fid)
        described.append(match[1])
    return ids, described, unknown


SETUP_HINT = (
    'Set RAPIDAPI_KEY in .env and subscribe that key to "booking-com15" on '
    'rapidapi.com (free BASIC plan) to enable live rates.'
)


class HotelRatesTool(ToolBase):
    """Live hotel rates and photos. Fails loudly rather than inventing data."""

    def __init__(self, api_key: Optional[str] = None, timeout: int = 30,
                 cache_dir: Optional[str] = None):
        self._api_key = api_key if api_key is not None else os.getenv('RAPIDAPI_KEY', '')
        self._timeout = timeout
        self._cache_dir = os.path.abspath(cache_dir or CACHE_DIR)
        os.makedirs(self._cache_dir, exist_ok=True)
        self._lock = threading.Lock()
        self._session = requests.Session()

    @property
    def name(self) -> str:
        return 'hotel_rates'

    @property
    def description(self) -> str:
        return 'Live hotel prices, review scores and real photos from Booking.com'

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    @property
    def capabilities(self) -> List[ToolCapability]:
        return [
            ToolCapability(
                name='search_hotels',
                description=(
                    'Search real bookable hotels with REAL nightly rates, review scores '
                    'and photographs. Use this when the traveller needs prices.'
                ),
                parameters={
                    'destination': 'City or area name, e.g. "Ubud, Bali"',
                    'check_in': 'Check-in date YYYY-MM-DD',
                    'check_out': 'Check-out date YYYY-MM-DD',
                    'adults': 'Number of adults (default 2)',
                    'children': 'Number of children (default 0)',
                    'rooms': 'Number of rooms (default 1)',
                    'currency': 'Currency code (default USD)',
                    'min_review_score': 'Only hotels scoring at least this /10 (optional)',
                    'max_price': 'Only hotels at or below this total price (optional)',
                    'needs': ('Comma-separated traveller needs the provider can filter on: '
                              'family, kids, wheelchair, step_free, elderly, pool, '
                              'breakfast, well_reviewed, top_reviewed'),
                },
                returns='list[HotelOffer]',
                required=['destination', 'check_in', 'check_out'],
            ),
            ToolCapability(
                name='get_hotel_photos',
                description='Get all real photographs Booking.com holds for one hotel',
                parameters={'hotel_id': 'Booking.com hotel id from search_hotels'},
                returns='list[Photo]',
                required=['hotel_id'],
            ),
        ]

    def execute(self, capability: str, params: Dict[str, Any]) -> ToolResult:
        if capability == 'search_hotels':
            return self.search_hotels(params)
        if capability == 'get_hotel_photos':
            return self.get_hotel_photos(params)
        raise ToolError(f"Unknown capability: {capability}",
                        tool_name=self.name, capability=capability)

    # ── HTTP with cache ──────────────────────────────────────────

    def _cache_path(self, path: str, params: Dict[str, Any]) -> str:
        key = hashlib.sha1(f'{path}|{sorted(params.items())}'.encode()).hexdigest()[:20]
        return os.path.join(self._cache_dir, f'{key}.json')

    @staticmethod
    def _ttl_for(path: str) -> int:
        return ENDPOINT_TTL.get(path, CACHE_TTL)

    # ── daily spend ledger ───────────────────────────────────────

    @property
    def _ledger_path(self) -> str:
        return os.path.join(self._cache_dir, '_calls.json')

    def _ledger(self) -> Dict[str, Any]:
        try:
            with open(self._ledger_path) as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return {}

    def _today(self) -> str:
        return datetime.utcnow().strftime('%Y-%m-%d')

    def spend_today(self) -> int:
        return int(self._ledger().get(self._today(), 0))

    def _record_call(self) -> None:
        with self._lock:
            ledger = self._ledger()
            today = self._today()
            ledger[today] = int(ledger.get(today, 0)) + 1
            # Keep a week of history for the settings panel, drop the rest.
            for day in sorted(ledger)[:-7]:
                ledger.pop(day, None)
            try:
                with open(self._ledger_path, 'w') as fh:
                    json.dump(ledger, fh)
            except OSError as exc:
                logger.warning('Could not write the call ledger: %s', exc)

    # ── the provider's own allowance ─────────────────────────────

    @property
    def _quota_path(self) -> str:
        return os.path.join(self._cache_dir, '_quota.json')

    def provider_quota(self) -> Dict[str, Any]:
        """Last reported allowance: limit, remaining and when it resets."""
        try:
            with open(self._quota_path) as fh:
                quota = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return {}
        # Once the reset time passes the allowance is fresh again.
        if quota.get('reset_at') and time.time() > quota['reset_at']:
            return {}
        return quota

    def _record_quota(self, headers) -> None:
        lower = {k.lower(): v for k, v in headers.items()}
        if 'x-ratelimit-requests-remaining' not in lower:
            return
        try:
            quota = {
                'limit': int(lower.get('x-ratelimit-requests-limit', 0)),
                'remaining': int(lower['x-ratelimit-requests-remaining']),
                'reset_at': time.time() + int(lower.get('x-ratelimit-requests-reset', 0)),
                'seen_at': time.time(),
            }
        except (TypeError, ValueError):
            return
        try:
            with open(self._quota_path, 'w') as fh:
                json.dump(quota, fh)
        except OSError as exc:
            logger.warning('Could not write the quota record: %s', exc)

    def budget_left(self) -> int:
        """Live calls we can still make, by the stricter of the two limits."""
        quota = self.provider_quota()
        if quota and quota.get('remaining') is not None:
            provider_left = max(0, int(quota['remaining']))
            # An old zero is a guess, not a fact: allow one probe so an
            # upgraded plan is noticed instead of being locked out until reset.
            if provider_left == 0 and \
                    time.time() - quota.get('seen_at', 0) > EXHAUSTED_RECHECK:
                provider_left = 1
        else:
            provider_left = None

        local_left = max(0, DAILY_LIMIT - self.spend_today()) if DAILY_LIMIT > 0 else 0
        if provider_left is None:
            return local_left
        return min(provider_left, local_left)

    def cache_stats(self) -> Dict[str, Any]:
        """What the settings panel shows about the metered provider."""
        entries = []
        for name in os.listdir(self._cache_dir) if os.path.isdir(self._cache_dir) else []:
            if not name.endswith('.json') or name.startswith('_'):
                continue
            full = os.path.join(self._cache_dir, name)
            try:
                entries.append(time.time() - os.path.getmtime(full))
            except OSError:
                continue
        quota = self.provider_quota()
        resets_in = (quota.get('reset_at', 0) - time.time()) if quota.get('reset_at') else 0
        return {
            'configured': self.configured,
            'provider_limit': quota.get('limit'),
            'provider_remaining': quota.get('remaining'),
            'provider_resets_in_days': round(resets_in / 86400, 1) if resets_in > 0 else None,
            'exhausted': bool(quota) and quota.get('remaining') == 0,
            'cached_responses': len(entries),
            'oldest_hours': round(max(entries) / 3600, 1) if entries else 0,
            'newest_minutes': round(min(entries) / 60, 1) if entries else 0,
            'calls_today': self.spend_today(),
            'daily_limit': DAILY_LIMIT,
            'calls_left_today': self.budget_left(),
            'history': self._ledger(),
            'rate_ttl_hours': round(CACHE_TTL / 3600, 1),
        }

    def recheck_quota(self) -> Dict[str, Any]:
        """Forget what we think the allowance is, so the next call re-reads it."""
        try:
            os.remove(self._quota_path)
        except OSError:
            pass
        return {'rechecked': True}

    def clear_cache(self) -> Dict[str, Any]:
        """Explicit reset from settings — the next search fetches fresh."""
        removed = 0
        if os.path.isdir(self._cache_dir):
            for name in os.listdir(self._cache_dir):
                if name.endswith('.json') and not name.startswith('_'):
                    try:
                        os.remove(os.path.join(self._cache_dir, name))
                        removed += 1
                    except OSError:
                        pass
        return {'cleared': removed, 'calls_today': self.spend_today()}

    def _get(self, path: str, params: Dict[str, Any]) -> Tuple[Optional[Dict], Provenance]:
        """GET with disk cache. Returns (payload, provenance)."""
        url = f'{BASE}{path}'

        if not self._api_key:
            return None, Provenance('booking_rapidapi', SourceStatus.NOT_CONFIGURED,
                                    url=url, detail=SETUP_HINT)

        cache_file = self._cache_path(path, params)
        cached, age_s = self._read_cache(cache_file)
        ttl = self._ttl_for(path)

        if cached is not None and age_s < ttl:
            return cached, Provenance(
                'booking_rapidapi', SourceStatus.CACHED, url=url,
                attribution=ATTRIBUTION,
                detail=f'cached {self._age_label(age_s)} ago; not re-fetched for {ttl // 3600}h')

        # Past the daily ceiling, stale data beats spending a quota the
        # traveller cannot see — as long as we say it is stale.
        if self.budget_left() <= 0:
            quota = self.provider_quota()
            resets = quota.get('reset_at', 0) - time.time()
            why = (f"the Booking.com plan's {quota.get('limit')} monthly requests are "
                   f"used up (resets in {resets / 86400:.0f} days)"
                   if quota else f'the local cap of {DAILY_LIMIT} lookups a day is reached')
            if cached is not None:
                return cached, Provenance(
                    'booking_rapidapi', SourceStatus.CACHED, url=url,
                    attribution=ATTRIBUTION,
                    detail=(f'STALE: cached {self._age_label(age_s)} ago and not '
                            f'refreshed, because {why}.'))
            return None, Provenance(
                'booking_rapidapi', SourceStatus.UNAVAILABLE, url=url,
                detail=(f'No prices for this search: nothing matching is cached and '
                        f'{why}.'))

        try:
            with self._lock:
                resp = self._session.get(
                    url, params=params, timeout=self._timeout,
                    headers={'x-rapidapi-key': self._api_key, 'x-rapidapi-host': RAPIDAPI_HOST},
                )
        except requests.RequestException as exc:
            return None, Provenance('booking_rapidapi', SourceStatus.FAILED, url=url,
                                    detail=f'{type(exc).__name__}: {exc}')

        self._record_quota(resp.headers)

        if resp.status_code == 403:
            return None, Provenance('booking_rapidapi', SourceStatus.NOT_CONFIGURED, url=url,
                                    detail=f'RapidAPI key is not subscribed to {RAPIDAPI_HOST}. {SETUP_HINT}')
        if resp.status_code == 429:
            quota = self.provider_quota()
            resets = quota.get('reset_at', 0) - time.time()
            when = (f', resets in {resets / 86400:.0f} days' if resets > 0 else '')
            return None, Provenance(
                'booking_rapidapi', SourceStatus.UNAVAILABLE, url=url,
                detail=(f"The Booking.com plan's allowance of "
                        f"{quota.get('limit', 'its monthly')} requests is used up"
                        f"{when}. Cached prices still work."))
        if resp.status_code != 200:
            return None, Provenance('booking_rapidapi', SourceStatus.FAILED, url=url,
                                    detail=f'HTTP {resp.status_code}: {resp.text[:160]}')

        try:
            payload = resp.json()
        except json.JSONDecodeError:
            return None, Provenance('booking_rapidapi', SourceStatus.FAILED, url=url,
                                    detail='provider returned non-JSON')

        self._record_call()
        try:
            with open(cache_file, 'w') as fh:
                json.dump(payload, fh)
        except OSError as exc:
            logger.warning('Could not write rate cache: %s', exc)

        return payload, Provenance(
            'booking_rapidapi', SourceStatus.LIVE, url=url, attribution=ATTRIBUTION,
            detail=f'{self.budget_left()} of {DAILY_LIMIT} live lookups left today')

    # ── destination resolution ───────────────────────────────────

    def _resolve_destination(self, destination: str) -> Tuple[Optional[Dict], Provenance]:
        payload, prov = self._get('/hotels/searchDestination', {'query': destination})
        if payload is None:
            return None, prov
        results = payload.get('data') or []
        if not results:
            return None, Provenance('booking_rapidapi', SourceStatus.UNAVAILABLE,
                                    detail=f'Booking.com does not recognise {destination!r}')
        # Prefer a city over a broad region — region results dilute relevance.
        cities = [r for r in results if r.get('search_type') == 'city']
        return (cities[0] if cities else results[0]), prov

    # ── search ───────────────────────────────────────────────────

    def search_hotels(self, params: Dict[str, Any]) -> ToolResult:
        destination = params.get('destination', '')
        check_in = params.get('check_in', '')
        check_out = params.get('check_out', '')

        missing = [k for k, v in (('destination', destination), ('check_in', check_in),
                                  ('check_out', check_out)) if not v]
        if missing:
            return ToolResult(status=ToolStatus.ERROR,
                              message=f"Missing required parameters: {', '.join(missing)}",
                              error='Missing parameters')

        nights = self._nights(check_in, check_out)
        if nights < 1:
            return ToolResult(status=ToolStatus.ERROR,
                              message='check_out must be after check_in', error='Invalid dates')

        raw_needs = params.get('needs') or []
        if isinstance(raw_needs, str):
            raw_needs = [n for n in raw_needs.replace(',', ' ').split() if n]
        filter_ids, described, unknown = filters_for(raw_needs)

        dest, dest_prov = self._resolve_destination(destination)
        if dest is None:
            return self._degraded(dest_prov, destination,
                                  f'Could not look up {destination!r} on Booking.com')

        payload, prov = self._get('/hotels/searchHotels', {
            'dest_id': dest.get('dest_id'),
            'search_type': dest.get('search_type'),
            'arrival_date': check_in,
            'departure_date': check_out,
            'adults': str(params.get('adults', 2) or 2),
            'children_age': ','.join(['8'] * int(params.get('children', 0) or 0)) or None,
            'room_qty': str(params.get('rooms', 1) or 1),
            'page_number': '1',
            'units': 'metric',
            'currency_code': params.get('currency', 'USD') or 'USD',
            'languagecode': 'en-us',
            'categories_filter': ','.join(filter_ids) or None,
        })
        if payload is None:
            return self._degraded(prov, destination,
                                  f'Live rates unavailable for {destination}')

        raw = (payload.get('data') or {}).get('hotels') or []
        min_score = float(params.get('min_review_score') or 0)
        max_price = float(params.get('max_price') or 0)

        hotels = []
        for item in raw:
            hotel = self._normalize(item, check_in, check_out, nights, prov)
            if not hotel:
                continue
            if min_score and (hotel['review_score'] or 0) < min_score:
                continue
            if max_price and hotel['total_price'] and hotel['total_price'] > max_price:
                continue
            hotels.append(hotel)

        if not hotels:
            note = 'no hotels matched your filters' if raw else 'Booking.com returned no availability'
            return ToolResult(
                status=ToolStatus.NO_RESULTS,
                data={'destination': destination, 'hotels': [], 'provenance': prov.to_dict()},
                message=f'{note} for {destination} on {check_in}→{check_out}',
            )

        hotels.sort(key=lambda h: h['total_price'] or 1e9)
        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                'destination': destination,
                'resolved_as': dest.get('label', destination),
                'check_in': check_in, 'check_out': check_out, 'nights': nights,
                'hotels': hotels, 'count': len(hotels),
                'has_prices': True,
                'filtered_for': described,
                # Say plainly what could not be filtered rather than implying
                # the results honour a need they were never checked against.
                'unsupported_needs': unknown,
                'provenance': prov.to_dict(),
            },
            message=(f'{len(hotels)} bookable hotels in {dest.get("label", destination)} '
                     f'({nights} nights, {prov.status.value})'
                     + (f' filtered for {", ".join(described)}' if described else '')
                     + (f'; cannot filter on {", ".join(unknown)}' if unknown else '')),
        )

    def _degraded(self, prov: Provenance, destination: str, headline: str) -> ToolResult:
        """A failure that states what is missing instead of inventing hotels."""
        return ToolResult(
            status=ToolStatus.ERROR,
            data={'destination': destination, 'hotels': [], 'has_prices': False,
                  'provenance': prov.to_dict()},
            message=f'{headline}. {prov.detail}',
            error=prov.detail,
        )

    def _normalize(self, item: Dict[str, Any], check_in: str, check_out: str,
                   nights: int, prov: Provenance) -> Optional[Dict[str, Any]]:
        prop = item.get('property') or {}
        name = prop.get('name')
        if not name:
            return None

        gross = ((prop.get('priceBreakdown') or {}).get('grossPrice') or {})
        total = gross.get('value')
        currency = gross.get('currency', 'USD')
        excluded = ((prop.get('priceBreakdown') or {}).get('excludedPrice') or {}).get('value')

        stars = prop.get('accuratePropertyClass') or prop.get('propertyClass') or None
        photos = [p for p in (prop.get('photoUrls') or []) if p]
        # square500 is a thumbnail; max1024x768 is the same real photo, larger.
        photos = [p.replace('square500', 'max1024x768') for p in photos]

        record = {
            'hotel_id': str(item.get('hotel_id') or prop.get('id') or ''),
            'name': name,
            'area': prop.get('wishlistName', ''),
            'stars': stars,
            'review_score': prop.get('reviewScore'),
            'review_count': prop.get('reviewCount'),
            'review_word': prop.get('reviewScoreWord', ''),
            'lat': prop.get('latitude'),
            'lon': prop.get('longitude'),
            'country': prop.get('countryCode', ''),
            'check_in': check_in,
            'check_out': check_out,
            'nights': nights,
            'total_price': round(total, 2) if isinstance(total, (int, float)) else None,
            'price_per_night': round(total / nights, 2) if isinstance(total, (int, float)) and nights else None,
            'taxes_excluded': round(excluded, 2) if isinstance(excluded, (int, float)) else None,
            'currency': currency,
            # Both ends of each window: '00:00' as an until-time means
            # midnight, not the hour you may arrive.
            'checkin_from': (prop.get('checkin') or {}).get('fromTime', ''),
            'checkin_until': (prop.get('checkin') or {}).get('untilTime', ''),
            'checkout_from': (prop.get('checkout') or {}).get('fromTime', ''),
            'checkout_until': (prop.get('checkout') or {}).get('untilTime', ''),
            'image_url': photos[0] if photos else None,
            'photos': photos[:6],
            'booking_url': f"https://www.booking.com/hotel/{prop.get('countryCode','')}/{name.lower().replace(' ', '-')}.html",
            'summary': item.get('accessibilityLabel', '')[:400],
            'bookable': True,
        }
        return stamp(record, prov)

    # ── photos ───────────────────────────────────────────────────

    def get_hotel_photos(self, params: Dict[str, Any]) -> ToolResult:
        hotel_id = str(params.get('hotel_id', '')).strip()
        if not hotel_id:
            return ToolResult(status=ToolStatus.ERROR, message='hotel_id is required',
                              error='Missing hotel_id')

        payload, prov = self._get('/hotels/getHotelPhotos', {'hotel_id': hotel_id})
        if payload is None:
            return ToolResult(status=ToolStatus.ERROR,
                              data={'photos': [], 'provenance': prov.to_dict()},
                              message=f'Could not fetch photos for hotel {hotel_id}. {prov.detail}',
                              error=prov.detail)

        data = payload.get('data')
        urls: List[str] = []
        if isinstance(data, list):
            for entry in data:
                url = entry.get('url') if isinstance(entry, dict) else entry
                if isinstance(url, str):
                    urls.append(url)
        elif isinstance(data, dict):
            urls = [u for u in data.values() if isinstance(u, str)]

        if not urls:
            return ToolResult(status=ToolStatus.NO_RESULTS,
                              data={'photos': [], 'provenance': prov.to_dict()},
                              message=f'Booking.com has no photos for hotel {hotel_id}')

        return ToolResult(status=ToolStatus.SUCCESS,
                          data={'hotel_id': hotel_id, 'photos': urls[:20],
                                'count': len(urls), 'provenance': prov.to_dict()},
                          message=f'{len(urls)} real photographs')

    @staticmethod
    def _read_cache(path: str):
        """Return (payload, age_seconds), or (None, inf) when unusable."""
        try:
            with open(path) as fh:
                return json.load(fh), time.time() - os.path.getmtime(path)
        except (OSError, json.JSONDecodeError):
            return None, float('inf')

    @staticmethod
    def _age_label(seconds: float) -> str:
        if seconds < 3600:
            return f'{int(seconds / 60)} min'
        if seconds < 86400:
            return f'{seconds / 3600:.1f} h'
        return f'{seconds / 86400:.1f} days'

    @staticmethod
    def _nights(check_in: str, check_out: str) -> int:
        try:
            return (datetime.strptime(check_out, '%Y-%m-%d')
                    - datetime.strptime(check_in, '%Y-%m-%d')).days
        except ValueError:
            return 0
