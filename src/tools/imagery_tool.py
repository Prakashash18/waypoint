"""ImageryTool — real pictures of real places, or nothing at all.

Three ways to show a traveller what a place actually looks like, tried in
order of how much it tells them:

  1. website  — a live headless screenshot of the hotel's own site
  2. map      — a rendered OpenStreetMap view centred on the hotel's coordinates
  3. photo    — a geotagged Wikimedia Commons photograph taken nearby

If all three fail the tool returns no image and says why. It never substitutes
a stock photo, because a stock photo of "a pool" is a lie about this hotel.

Capabilities: capture_hotel_view, find_photos
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from .base import ToolBase, ToolCapability, ToolError, ToolResult, ToolStatus
from .provenance import Provenance, SourceStatus, stamp

logger = logging.getLogger(__name__)

USER_AGENT = 'Waypoint/1.0 (travel planning agent; +https://github.com/waypoint)'
BROWSER_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36')

# Overridable so a container can put captures on a mounted disk.
CAPTURE_DIR = os.getenv(
    'WAYPOINT_CAPTURE_DIR',
    os.path.join(os.path.dirname(__file__), '..', 'ui', 'static', 'captures'))
CAPTURE_URL_PREFIX = '/static/captures'

COMMONS_API = 'https://commons.wikimedia.org/w/api.php'

# The page loaded, but what we got is not the hotel.
BOT_WALL_MARKERS = (
    'just a moment', 'attention required', 'checking your browser',
    'enable javascript and cookies', 'access denied', 'are you a robot',
    'verifying you are human', '403 forbidden',
)
# The hotel's own server is broken or gone — distinct from being blocked,
# and worth saying accurately in the trace.
DEAD_SITE_MARKERS = (
    'connection timed out', '522:', '523:', '521:', 'web server is down',
    'origin is unreachable', 'this site can', 'domain for sale',
    'account suspended', 'under construction', '404 not found',
)

# A Leaflet page we render ourselves — no API key, tiles straight from OSM.
MAP_HTML = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body,#m{{margin:0;height:100%;width:100%}}
.lbl{{background:#111;color:#fff;padding:6px 10px;border-radius:6px;
font:600 13px system-ui;white-space:nowrap}}</style></head>
<body><div id="m"></div><script>
var m=L.map('m',{{zoomControl:false,attributionControl:true}}).setView([{lat},{lon}],{zoom});
L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
{{maxZoom:19,attribution:'© OpenStreetMap contributors'}}).addTo(m);
L.marker([{lat},{lon}]).addTo(m).bindTooltip({name!r},
{{permanent:true,direction:'top',className:'lbl'}}).openTooltip();
window.__ready=true;
</script></body></html>"""


class ImageryTool(ToolBase):
    """Captures real imagery of real coordinates."""

    # Playwright's sync API is not re-entrant; serialise browser work.
    _browser_lock = threading.Lock()

    def __init__(self, capture_dir: Optional[str] = None, timeout: int = 30):
        self._dir = os.path.abspath(capture_dir or CAPTURE_DIR)
        os.makedirs(self._dir, exist_ok=True)
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({'User-Agent': USER_AGENT})

    @property
    def name(self) -> str:
        return 'imagery'

    @property
    def description(self) -> str:
        return 'Capture real screenshots and photographs of real locations'

    @property
    def capabilities(self) -> List[ToolCapability]:
        return [
            ToolCapability(
                name='capture_hotel_view',
                description=(
                    "Get a real image of a specific hotel: a live screenshot of its own "
                    "website, else a map of its exact coordinates, else a nearby "
                    "geotagged photo. Returns no image rather than a fake one."
                ),
                parameters={
                    'name': 'Hotel name',
                    'website': 'Hotel website URL (optional)',
                    'lat': 'Latitude (optional but strongly preferred)',
                    'lon': 'Longitude (optional)',
                    'prefer': 'website | map | photo (default website)',
                },
                returns='HotelImage',
            ),
            ToolCapability(
                name='find_photos',
                description='Find real geotagged photographs near given coordinates',
                parameters={
                    'lat': 'Latitude', 'lon': 'Longitude',
                    'radius_m': 'Search radius in metres (default 3000, max 10000)',
                    'limit': 'Max photos (default 5)',
                },
                returns='list[Photo]',
            ),
        ]

    def execute(self, capability: str, params: Dict[str, Any]) -> ToolResult:
        if capability == 'capture_hotel_view':
            return self.capture_hotel_view(params)
        if capability == 'find_photos':
            return self.find_photos(params)
        raise ToolError(f"Unknown capability: {capability}",
                        tool_name=self.name, capability=capability)

    # ── orchestration ────────────────────────────────────────────

    def capture_hotel_view(self, params: Dict[str, Any]) -> ToolResult:
        name = params.get('name', '') or 'this place'
        website = params.get('website') or ''
        lat, lon = params.get('lat'), params.get('lon')
        prefer = (params.get('prefer') or 'website').lower()

        attempts: List[Dict[str, str]] = []

        order = ['website', 'map', 'photo']
        if prefer in order:
            order.remove(prefer)
            order.insert(0, prefer)

        for mode in order:
            if mode == 'website' and website:
                image, prov, why = self._shoot_website(website, name)
            elif mode == 'map' and lat is not None and lon is not None:
                image, prov, why = self._shoot_map(float(lat), float(lon), name)
            elif mode == 'photo' and lat is not None and lon is not None:
                image, prov, why = self._nearby_photo(float(lat), float(lon))
            else:
                attempts.append({'mode': mode, 'result': 'skipped — inputs missing'})
                continue

            if image:
                image['capture_mode'] = mode
                image['attempts'] = attempts
                return ToolResult(status=ToolStatus.SUCCESS, data=stamp(image, prov),
                                  message=f'Captured {mode} view of {name}')
            attempts.append({'mode': mode, 'result': why})

        prov = Provenance('screenshot', SourceStatus.UNAVAILABLE,
                          detail='; '.join(f"{a['mode']}: {a['result']}" for a in attempts))
        return ToolResult(
            status=ToolStatus.NO_RESULTS,
            data={'name': name, 'image_url': None, 'attempts': attempts,
                  'provenance': prov.to_dict()},
            message=(f'No authentic image available for {name}. '
                     f'I will not substitute a stock photo.'),
        )

    # ── 1. live website screenshot ───────────────────────────────

    def _shoot_website(self, url: str, name: str) -> Tuple[Optional[Dict], Optional[Provenance], str]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return None, None, 'playwright not installed (pip install playwright)'

        slug = hashlib.sha1(f'{url}|{name}'.encode()).hexdigest()[:16]
        path = os.path.join(self._dir, f'site_{slug}.png')

        # Serve an existing capture rather than re-hitting the hotel's server.
        if os.path.exists(path) and time.time() - os.path.getmtime(path) < 86400:
            prov = Provenance('screenshot', SourceStatus.CACHED, url=url,
                              attribution=f'Screenshot of {url}',
                              detail='cached within 24h')
            return self._image_record(path, name, url, 'website'), prov, ''

        with self._browser_lock:
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(args=['--disable-blink-features=AutomationControlled'])
                    ctx = browser.new_context(viewport={'width': 1280, 'height': 800},
                                              user_agent=BROWSER_UA, locale='en-US')
                    page = ctx.new_page()
                    try:
                        page.goto(url, wait_until='domcontentloaded', timeout=self._timeout * 1000)
                        page.wait_for_timeout(2500)
                        self._dismiss_cookie_banners(page)
                        title = (page.title() or '').lower()
                        body = (page.inner_text('body')[:1500] or '').lower()
                        haystack = f'{title} {body[:400]}'
                        if any(m in haystack for m in DEAD_SITE_MARKERS):
                            return None, None, (f"the hotel's own site is down "
                                                f"({page.title()[:50]!r})")
                        if any(m in haystack for m in BOT_WALL_MARKERS):
                            return None, None, (f'site blocks automated visits '
                                                f'({page.title()[:40]!r})')
                        page.screenshot(path=path)
                        real_title = page.title()
                    finally:
                        ctx.close()
                        browser.close()
            except Exception as exc:
                detail = str(exc)
                if 'ERR_NAME_NOT_RESOLVED' in detail:
                    return None, None, f'the domain {url} no longer exists'
                if 'ERR_CONNECTION' in detail or 'Timeout' in type(exc).__name__:
                    return None, None, f'{url} did not respond'
                return None, None, f'{type(exc).__name__}: {detail[:110]}'

        if not os.path.exists(path) or os.path.getsize(path) < 8000:
            return None, None, 'screenshot was blank or too small'

        prov = Provenance('screenshot', SourceStatus.LIVE, url=url,
                          attribution=f'Live screenshot of {url}',
                          detail=f'page title: {real_title[:80]}')
        rec = self._image_record(path, name, url, 'website')
        rec['page_title'] = real_title
        return rec, prov, ''

    @staticmethod
    def _dismiss_cookie_banners(page) -> None:
        """Click obvious consent buttons so they do not cover the photograph.

        Only cosmetic dismissal of our own throwaway browser context — nothing
        is submitted and no account is involved.
        """
        for label in ('Accept', 'Accept all', 'I agree', 'Got it', 'OK', 'Allow all'):
            try:
                btn = page.get_by_role('button', name=label, exact=False).first
                if btn.is_visible(timeout=600):
                    btn.click(timeout=1200)
                    page.wait_for_timeout(500)
                    return
            except Exception:
                continue

    # ── 2. map of the exact coordinates ──────────────────────────

    def _shoot_map(self, lat: float, lon: float, name: str,
                   zoom: int = 16) -> Tuple[Optional[Dict], Optional[Provenance], str]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return None, None, 'playwright not installed'

        slug = hashlib.sha1(f'{lat:.5f},{lon:.5f},{zoom}'.encode()).hexdigest()[:16]
        path = os.path.join(self._dir, f'map_{slug}.png')

        if os.path.exists(path) and time.time() - os.path.getmtime(path) < 604800:
            prov = Provenance('osm_tiles', SourceStatus.CACHED, license='ODbL',
                              attribution='© OpenStreetMap contributors')
            return self._image_record(path, name, '', 'map'), prov, ''

        html = MAP_HTML.format(lat=lat, lon=lon, zoom=zoom, name=name)
        with self._browser_lock:
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page(viewport={'width': 900, 'height': 600})
                    try:
                        page.set_content(html, wait_until='load', timeout=self._timeout * 1000)
                        # Give the tile layer time to actually paint.
                        page.wait_for_timeout(3500)
                        page.screenshot(path=path)
                    finally:
                        browser.close()
            except Exception as exc:
                return None, None, f'{type(exc).__name__}: {str(exc)[:120]}'

        if not os.path.exists(path) or os.path.getsize(path) < 5000:
            return None, None, 'map render was blank'

        prov = Provenance('osm_tiles', SourceStatus.LIVE, license='ODbL',
                          url=f'https://www.openstreetmap.org/#map={zoom}/{lat}/{lon}',
                          attribution='© OpenStreetMap contributors',
                          detail=f'map centred on {lat:.5f},{lon:.5f}')
        rec = self._image_record(path, name, '', 'map')
        rec['lat'], rec['lon'] = lat, lon
        return rec, prov, ''

    # ── 3. nearby geotagged photograph ───────────────────────────

    def _nearby_photo(self, lat: float, lon: float) -> Tuple[Optional[Dict], Optional[Provenance], str]:
        res = self.find_photos({'lat': lat, 'lon': lon, 'radius_m': 3000, 'limit': 1})
        if not res.is_success() or not res.data.get('photos'):
            return None, None, res.message
        photo = res.data['photos'][0]
        prov = Provenance('wikimedia', SourceStatus.LIVE, url=photo['descriptionurl'],
                          license=photo.get('license', 'see Commons'),
                          attribution=photo.get('attribution', 'Wikimedia Commons'),
                          detail=f"geotagged photo {photo['distance_km']}km away")
        return ({'name': photo['title'], 'image_url': photo['url'],
                 'local_path': None, 'width': photo.get('width'),
                 'is_remote': True, 'source_url': photo['descriptionurl']}, prov, '')

    def find_photos(self, params: Dict[str, Any]) -> ToolResult:
        lat, lon = params.get('lat'), params.get('lon')
        if lat is None or lon is None:
            return ToolResult(status=ToolStatus.ERROR, message='lat and lon are required',
                              error='Missing coordinates')
        radius = min(int(params.get('radius_m', 3000) or 3000), 10000)
        limit = int(params.get('limit', 5) or 5)

        try:
            resp = self._session.get(COMMONS_API, timeout=self._timeout, params={
                'action': 'query', 'generator': 'geosearch',
                'ggscoord': f'{lat}|{lon}', 'ggsradius': radius,
                'ggslimit': limit, 'ggsnamespace': 6,
                'prop': 'imageinfo', 'iiprop': 'url|extmetadata',
                'iiurlwidth': 1024, 'format': 'json',
            })
        except requests.RequestException as exc:
            prov = Provenance('wikimedia', SourceStatus.FAILED, detail=str(exc))
            return ToolResult(status=ToolStatus.ERROR, data={'provenance': prov.to_dict()},
                              message=f'Could not reach Wikimedia Commons: {exc}', error=str(exc))

        pages = (resp.json().get('query') or {}).get('pages', {}) if resp.status_code == 200 else {}
        photos = []
        for page in pages.values():
            info = (page.get('imageinfo') or [{}])[0]
            if not info.get('thumburl'):
                continue
            meta = info.get('extmetadata', {}) or {}
            photos.append({
                'title': page.get('title', '').replace('File:', ''),
                'url': info['thumburl'],
                'descriptionurl': info.get('descriptionurl', ''),
                'width': info.get('thumbwidth'),
                'license': (meta.get('LicenseShortName') or {}).get('value', ''),
                'attribution': (meta.get('Artist') or {}).get('value', 'Wikimedia Commons')[:200],
                'distance_km': round(radius / 1000, 1),
            })

        if not photos:
            prov = Provenance('wikimedia', SourceStatus.UNAVAILABLE,
                              detail=f'no geotagged photos within {radius}m')
            return ToolResult(status=ToolStatus.NO_RESULTS,
                              data={'photos': [], 'provenance': prov.to_dict()},
                              message=f'No geotagged photographs within {radius}m')

        prov = Provenance('wikimedia', SourceStatus.LIVE, url=COMMONS_API,
                          license='various (see each file)',
                          attribution='Wikimedia Commons contributors')
        return ToolResult(status=ToolStatus.SUCCESS,
                          data={'photos': photos, 'count': len(photos),
                                'provenance': prov.to_dict()},
                          message=f'Found {len(photos)} real geotagged photographs')

    # ── helpers ──────────────────────────────────────────────────

    def _image_record(self, path: str, name: str, source_url: str, mode: str) -> Dict[str, Any]:
        return {
            'name': name,
            'image_url': f'{CAPTURE_URL_PREFIX}/{os.path.basename(path)}',
            'local_path': path,
            'bytes': os.path.getsize(path),
            'is_remote': False,
            'source_url': source_url,
            'capture_mode': mode,
        }
