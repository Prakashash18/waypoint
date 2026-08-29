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
CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '.cache', 'hotel_rates')
CACHE_TTL = 6 * 3600  # Rates move slowly enough that 6h is safe and saves quota.

ATTRIBUTION = 'Rates, review scores and photos from Booking.com via RapidAPI'

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
                },
                returns='list[HotelOffer]',
            ),
            ToolCapability(
                name='get_hotel_photos',
                description='Get all real photographs Booking.com holds for one hotel',
                parameters={'hotel_id': 'Booking.com hotel id from search_hotels'},
                returns='list[Photo]',
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

    def _get(self, path: str, params: Dict[str, Any]) -> Tuple[Optional[Dict], Provenance]:
        """GET with disk cache. Returns (payload, provenance)."""
        url = f'{BASE}{path}'

        if not self._api_key:
            return None, Provenance('booking_rapidapi', SourceStatus.NOT_CONFIGURED,
                                    url=url, detail=SETUP_HINT)

        cache_file = self._cache_path(path, params)
        if os.path.exists(cache_file) and time.time() - os.path.getmtime(cache_file) < CACHE_TTL:
            try:
                with open(cache_file) as fh:
                    payload = json.load(fh)
                age = int((time.time() - os.path.getmtime(cache_file)) / 60)
                return payload, Provenance('booking_rapidapi', SourceStatus.CACHED, url=url,
                                           attribution=ATTRIBUTION,
                                           detail=f'cached {age} min ago (free tier is metered)')
            except (json.JSONDecodeError, OSError):
                pass  # Corrupt cache entry — fall through and refetch.

        try:
            with self._lock:
                resp = self._session.get(
                    url, params=params, timeout=self._timeout,
                    headers={'x-rapidapi-key': self._api_key, 'x-rapidapi-host': RAPIDAPI_HOST},
                )
        except requests.RequestException as exc:
            return None, Provenance('booking_rapidapi', SourceStatus.FAILED, url=url,
                                    detail=f'{type(exc).__name__}: {exc}')

        if resp.status_code == 403:
            return None, Provenance('booking_rapidapi', SourceStatus.NOT_CONFIGURED, url=url,
                                    detail=f'RapidAPI key is not subscribed to {RAPIDAPI_HOST}. {SETUP_HINT}')
        if resp.status_code == 429:
            return None, Provenance('booking_rapidapi', SourceStatus.FAILED, url=url,
                                    detail='RapidAPI monthly quota exhausted for this key (HTTP 429)')
        if resp.status_code != 200:
            return None, Provenance('booking_rapidapi', SourceStatus.FAILED, url=url,
                                    detail=f'HTTP {resp.status_code}: {resp.text[:160]}')

        try:
            payload = resp.json()
        except json.JSONDecodeError:
            return None, Provenance('booking_rapidapi', SourceStatus.FAILED, url=url,
                                    detail='provider returned non-JSON')

        try:
            with open(cache_file, 'w') as fh:
                json.dump(payload, fh)
        except OSError as exc:
            logger.warning('Could not write rate cache: %s', exc)

        return payload, Provenance('booking_rapidapi', SourceStatus.LIVE, url=url,
                                   attribution=ATTRIBUTION)

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
                'provenance': prov.to_dict(),
            },
            message=(f'{len(hotels)} bookable hotels in {dest.get("label", destination)} '
                     f'({nights} nights, {prov.status.value})'),
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
            'checkin_from': (prop.get('checkin') or {}).get('fromTime', ''),
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
    def _nights(check_in: str, check_out: str) -> int:
        try:
            return (datetime.strptime(check_out, '%Y-%m-%d')
                    - datetime.strptime(check_in, '%Y-%m-%d')).days
        except ValueError:
            return 0
