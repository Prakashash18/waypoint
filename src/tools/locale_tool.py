"""LocaleTool — where the traveller actually is, and what money and clock they use.

Before this, the agent assumed Kuala Lumpur and quoted everything in USD. Both
are wrong for most people. This resolves the traveller's location from their IP
(or from browser coordinates when the page offers them), and reports the
currency and timezone that go with it, so fares and hotel rates are priced in
money they recognise and times can be shown against their own clock.

Capabilities: detect_locale
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

import requests

from .base import ToolBase, ToolCapability, ToolError, ToolResult, ToolStatus
from .provenance import Provenance, SourceStatus, stamp

logger = logging.getLogger(__name__)

USER_AGENT = 'Waypoint/1.0 (travel planning agent)'

# ip-api returns country, currency, timezone and coordinates in one free call.
IP_API = 'http://ip-api.com/json'
IP_API_FIELDS = ('status,message,country,countryCode,regionName,city,'
                 'lat,lon,timezone,offset,currency,query')

NOMINATIM_REVERSE = 'https://nominatim.openstreetmap.org/reverse'

# Browser coordinates are more precise than an IP but carry no currency, so a
# country still has to be mapped to money. Covers the common travel markets;
# anything unlisted falls back to the IP answer, then to USD.
COUNTRY_CURRENCY = {
    'SG': 'SGD', 'MY': 'MYR', 'ID': 'IDR', 'TH': 'THB', 'VN': 'VND',
    'PH': 'PHP', 'IN': 'INR', 'LK': 'LKR', 'JP': 'JPY', 'KR': 'KRW',
    'CN': 'CNY', 'HK': 'HKD', 'TW': 'TWD', 'AU': 'AUD', 'NZ': 'NZD',
    'GB': 'GBP', 'IE': 'EUR', 'FR': 'EUR', 'DE': 'EUR', 'ES': 'EUR',
    'IT': 'EUR', 'PT': 'EUR', 'NL': 'EUR', 'BE': 'EUR', 'AT': 'EUR',
    'GR': 'EUR', 'FI': 'EUR', 'CH': 'CHF', 'SE': 'SEK', 'NO': 'NOK',
    'DK': 'DKK', 'PL': 'PLN', 'CZ': 'CZK', 'TR': 'TRY', 'AE': 'AED',
    'SA': 'SAR', 'QA': 'QAR', 'ZA': 'ZAR', 'EG': 'EGP', 'KE': 'KES',
    'NG': 'NGN', 'US': 'USD', 'CA': 'CAD', 'MX': 'MXN', 'BR': 'BRL',
    'AR': 'ARS', 'CL': 'CLP', 'CO': 'COP', 'PE': 'PEN',
}

# Currencies conventionally written without decimal places.
ZERO_DECIMAL = {'JPY', 'KRW', 'VND', 'IDR', 'CLP', 'ISK'}

CURRENCY_SYMBOL = {
    'USD': '$', 'SGD': 'S$', 'MYR': 'RM', 'EUR': '€', 'GBP': '£',
    'JPY': '¥', 'CNY': '¥', 'HKD': 'HK$', 'AUD': 'A$', 'NZD': 'NZ$',
    'CAD': 'C$', 'INR': '₹', 'THB': '฿', 'IDR': 'Rp', 'PHP': '₱',
    'VND': '₫', 'KRW': '₩', 'TWD': 'NT$', 'CHF': 'CHF', 'AED': 'AED',
    'ZAR': 'R', 'BRL': 'R$', 'MXN': 'MX$',
}


class LocaleTool(ToolBase):
    """Resolves the traveller's location, currency and clock."""

    def __init__(self, timeout: int = 12):
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({'User-Agent': USER_AGENT})
        self._lock = threading.Lock()
        self._ip_cache: Optional[Dict[str, Any]] = None
        self._ip_cached_at: float = 0.0

    @property
    def name(self) -> str:
        return 'locale'

    @property
    def description(self) -> str:
        return "Detect where the traveller is, and the currency and timezone to use"

    @property
    def capabilities(self) -> List[ToolCapability]:
        return [
            ToolCapability(
                name='detect_locale',
                description=(
                    'Work out where the traveller is and which currency and timezone '
                    'to quote in. Pass lat/lon when the browser has shared them; '
                    'otherwise it falls back to their IP address.'
                ),
                parameters={
                    'lat': 'Latitude from the browser (optional, more accurate)',
                    'lon': 'Longitude from the browser (optional)',
                    'timezone': "The browser's own IANA timezone, e.g. Asia/Kuala_Lumpur (optional)",
                },
                returns='Locale',
            ),
        ]

    def execute(self, capability: str, params: Dict[str, Any]) -> ToolResult:
        if capability == 'detect_locale':
            return self.detect_locale(params)
        raise ToolError(f"Unknown capability: {capability}",
                        tool_name=self.name, capability=capability)

    # ── detection ────────────────────────────────────────────────

    def detect_locale(self, params: Dict[str, Any]) -> ToolResult:
        lat, lon = params.get('lat'), params.get('lon')
        browser_tz = (params.get('timezone') or '').strip()
        ip_info, ip_prov = self._from_ip()

        # The browser reports its own timezone exactly; trust it over the IP's.
        if browser_tz and ip_info:
            ip_info['timezone'] = browser_tz

        # Browser coordinates win on position; the IP answer still supplies
        # currency and timezone unless reverse geocoding disagrees on country.
        if lat is not None and lon is not None:
            precise = self._from_coords(float(lat), float(lon), ip_info)
            if precise:
                if browser_tz:
                    precise['timezone'] = browser_tz
                return ToolResult(status=ToolStatus.SUCCESS,
                                  data=stamp(precise, precise.pop('_prov')),
                                  message=self._describe(precise))

        if not ip_info:
            prov = ip_prov or Provenance('ip-api', SourceStatus.FAILED,
                                         detail='could not determine location')
            return ToolResult(
                status=ToolStatus.NO_RESULTS,
                data={'provenance': prov.to_dict(), 'currency': 'USD',
                      'currency_source': 'default', 'detected': False},
                message=('I could not work out where you are, so prices stay in USD '
                         'and times are shown at the airport local time.'),
            )

        return ToolResult(status=ToolStatus.SUCCESS,
                          data=stamp(ip_info, ip_prov),
                          message=self._describe(ip_info))

    def _from_ip(self):
        """Location from IP, cached — it does not change mid-session."""
        with self._lock:
            if self._ip_cache and time.time() - self._ip_cached_at < 1800:
                return dict(self._ip_cache), Provenance(
                    'ip-api', SourceStatus.CACHED, url=IP_API,
                    attribution='Location from ip-api.com')

        try:
            resp = self._session.get(IP_API, params={'fields': IP_API_FIELDS},
                                     timeout=self._timeout)
        except requests.RequestException as exc:
            return None, Provenance('ip-api', SourceStatus.FAILED, url=IP_API,
                                    detail=f'{type(exc).__name__}: {exc}')

        if resp.status_code != 200:
            return None, Provenance('ip-api', SourceStatus.FAILED, url=IP_API,
                                    detail=f'HTTP {resp.status_code}')

        body = resp.json()
        if body.get('status') != 'success':
            return None, Provenance('ip-api', SourceStatus.UNAVAILABLE, url=IP_API,
                                    detail=body.get('message', 'lookup failed'))

        country = body.get('countryCode', '')
        currency = body.get('currency') or COUNTRY_CURRENCY.get(country, 'USD')
        info = {
            'detected': True,
            'source': 'ip',
            'city': body.get('city', ''),
            'region': body.get('regionName', ''),
            'country': body.get('country', ''),
            'country_code': country,
            'lat': body.get('lat'),
            'lon': body.get('lon'),
            'timezone': body.get('timezone', ''),
            'utc_offset_seconds': body.get('offset', 0),
            'utc_offset_label': self._offset_label(body.get('offset', 0)),
            'currency': currency,
            'currency_symbol': CURRENCY_SYMBOL.get(currency, currency + ' '),
            'currency_decimals': 0 if currency in ZERO_DECIMAL else 2,
            'currency_source': 'ip',
            'precision': 'city',
        }

        with self._lock:
            self._ip_cache, self._ip_cached_at = dict(info), time.time()

        return info, Provenance('ip-api', SourceStatus.LIVE, url=IP_API,
                                attribution='Location from ip-api.com')

    def _from_coords(self, lat: float, lon: float,
                     ip_info: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Reverse geocode browser coordinates for a precise, consented location."""
        try:
            resp = self._session.get(
                NOMINATIM_REVERSE,
                params={'lat': lat, 'lon': lon, 'format': 'json', 'zoom': 10},
                timeout=self._timeout,
            )
            body = resp.json() if resp.status_code == 200 else {}
        except (requests.RequestException, ValueError):
            body = {}

        address = body.get('address') or {}
        country_code = (address.get('country_code') or '').upper()

        # Keep the IP's currency and timezone unless the country really differs.
        base = dict(ip_info or {})
        # Coordinates in a different country than the IP: none of the IP's
        # place names apply any more, so stop inheriting them.
        if country_code and base.get('country_code') and country_code != base['country_code']:
            base = {k: v for k, v in base.items()
                    if k not in ('city', 'region', 'country', 'timezone',
                                 'utc_offset_seconds', 'utc_offset_label')}
        currency = COUNTRY_CURRENCY.get(country_code) or base.get('currency') or 'USD'
        timezone = base.get('timezone', '') if (
            not country_code or country_code == base.get('country_code')) else ''

        info = {
            'detected': True,
            'source': 'browser',
            'city': address.get('city') or address.get('town') or address.get('village')
                    or address.get('municipality') or address.get('county')
                    or base.get('city', ''),
            'region': address.get('state', base.get('region', '')),
            'country': address.get('country', base.get('country', '')),
            'country_code': country_code or base.get('country_code', ''),
            'lat': lat,
            'lon': lon,
            'timezone': timezone or base.get('timezone', ''),
            'utc_offset_seconds': base.get('utc_offset_seconds', 0),
            'utc_offset_label': base.get('utc_offset_label', ''),
            'currency': currency,
            'currency_symbol': CURRENCY_SYMBOL.get(currency, currency + ' '),
            'currency_decimals': 0 if currency in ZERO_DECIMAL else 2,
            'currency_source': 'browser' if country_code else 'ip',
            'precision': 'gps',
            '_prov': Provenance('nominatim', SourceStatus.LIVE, url=NOMINATIM_REVERSE,
                                license='ODbL',
                                attribution='© OpenStreetMap contributors',
                                detail='reverse geocoded from browser coordinates'),
        }
        return info

    @staticmethod
    def _offset_label(seconds: int) -> str:
        try:
            seconds = int(seconds)
        except (TypeError, ValueError):
            return ''
        sign = '+' if seconds >= 0 else '−'
        seconds = abs(seconds)
        return f"UTC{sign}{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}"

    @staticmethod
    def _describe(info: Dict[str, Any]) -> str:
        where = ', '.join(filter(None, [info.get('city'), info.get('country')]))
        return (f"{where or 'Unknown location'} · prices in {info.get('currency')} "
                f"· {info.get('timezone') or 'timezone unknown'} "
                f"({info.get('utc_offset_label', '')})")
