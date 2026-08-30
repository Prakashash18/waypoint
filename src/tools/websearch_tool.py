"""WebSearchTool — work out what place someone meant.

The geocoder is exact: "Seminyk Bali" returns nothing at all, and the agent
would tell a traveller their destination does not exist. This resolves the
query first — Wikipedia corrects the spelling or interprets a description, and
the corrected name goes back through the geocoder for real coordinates.

No key is needed for any of that. A general web search sits behind the same
tool for genuinely open questions, and is only available when a provider key is
configured; without one it says so rather than pretending.

Capabilities: resolve_place, web_search
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import requests

from .base import ToolBase, ToolCapability, ToolError, ToolResult, ToolStatus
from .provenance import Provenance, SourceStatus, stamp

logger = logging.getLogger(__name__)

USER_AGENT = 'Waypoint/1.0 (travel planning agent; +https://github.com/waypoint)'
WIKI_API = 'https://en.wikipedia.org/w/api.php'
NOMINATIM = 'https://nominatim.openstreetmap.org/search'

# Optional general-search providers, in the order we would rather use them.
# Both have a free tier; neither is required for place resolution.
SEARCH_PROVIDERS = (
    ('brave', 'BRAVE_SEARCH_API_KEY', 'https://api.search.brave.com/res/v1/web/search'),
    ('tavily', 'TAVILY_API_KEY', 'https://api.tavily.com/search'),
)


class WebSearchTool(ToolBase):
    """Resolves vague or misspelt places, and searches the web when configured."""

    def __init__(self, timeout: int = 20):
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({'User-Agent': USER_AGENT})

    @property
    def name(self) -> str:
        return 'websearch'

    @property
    def description(self) -> str:
        return 'Work out what place someone meant, and search the web when configured'

    @property
    def capabilities(self) -> List[ToolCapability]:
        return [
            ToolCapability(
                name='resolve_place',
                description=(
                    'Work out which real place a query means when the geocoder cannot '
                    'find it — a misspelling ("Seminyk Bali"), or a description ("the '
                    'town with the rice terraces in Bali"). Returns the real name and '
                    'coordinates. Use this before telling anyone their destination '
                    'does not exist.'
                ),
                parameters={'query': 'Whatever the traveller called the place'},
                returns='ResolvedPlace',
                required=['query'],
            ),
            ToolCapability(
                name='web_search',
                description=(
                    'Search the web for something none of the travel sources cover — '
                    'a festival, an entry requirement, whether somewhere is walkable. '
                    'Needs a search provider key; without one it reports that plainly.'
                ),
                parameters={'query': 'What to search for',
                            'count': 'How many results (default 5, max 10)'},
                returns='list[SearchResult]',
                required=['query'],
            ),
        ]

    def execute(self, capability: str, params: Dict[str, Any]) -> ToolResult:
        if capability == 'resolve_place':
            return self.resolve_place(params)
        if capability == 'web_search':
            return self.web_search(params)
        raise ToolError(f"Unknown capability: {capability}",
                        tool_name=self.name, capability=capability)

    # ── place resolution ─────────────────────────────────────────

    def resolve_place(self, params: Dict[str, Any]) -> ToolResult:
        query = (params.get('query') or params.get('destination') or '').strip()
        if not query:
            return ToolResult(status=ToolStatus.ERROR, message='query is required',
                              error='Missing query')

        # Whatever the geocoder already accepts needs no interpreting.
        direct = self._geocode(query)
        if direct:
            prov = Provenance('nominatim', SourceStatus.LIVE, url=NOMINATIM,
                              license='ODbL',
                              attribution='© OpenStreetMap contributors',
                              detail='matched without interpretation')
            return ToolResult(status=ToolStatus.SUCCESS,
                              data=stamp({**direct, 'query': query,
                                          'corrected': False, 'interpretation': None}, prov),
                              message=f"{query} is {direct['display_name']}")

        candidates, how = self._interpret(query)
        if not candidates:
            prov = Provenance('wikipedia', SourceStatus.UNAVAILABLE, url=WIKI_API,
                              detail=f'nothing on Wikipedia resembling {query!r}')
            return ToolResult(
                status=ToolStatus.NO_RESULTS,
                data={'query': query, 'provenance': prov.to_dict()},
                message=(f'I could not work out what place {query!r} means — neither '
                         f'the map nor Wikipedia recognises it. Could you name the '
                         f'town or the country?'),
            )

        # Wikipedia corrected the name; the map still supplies the coordinates.
        for title in candidates:
            located = self._geocode(title)
            if located:
                prov = Provenance(
                    'wikipedia', SourceStatus.LIVE, url=WIKI_API,
                    license='CC BY-SA 4.0',
                    attribution='Interpreted via Wikipedia, located via OpenStreetMap',
                    detail=f'read {query!r} as {title!r} ({how})')
                return ToolResult(
                    status=ToolStatus.SUCCESS,
                    data=stamp({**located, 'query': query, 'corrected': True,
                                'interpretation': title, 'how': how,
                                'also_considered': [c for c in candidates if c != title][:2]},
                               prov),
                    message=(f'Read {query!r} as {title} — {located["display_name"]}'),
                )

        prov = Provenance('wikipedia', SourceStatus.UNAVAILABLE, url=WIKI_API,
                          detail=f'Wikipedia suggested {candidates[:2]} but none could be located')
        return ToolResult(
            status=ToolStatus.NO_RESULTS,
            data={'query': query, 'candidates': candidates, 'provenance': prov.to_dict()},
            message=(f'{query!r} might mean {" or ".join(candidates[:2])}, but the map '
                     f'has no coordinates for those. Could you be more specific?'),
        )

    def _interpret(self, query: str) -> Tuple[List[str], str]:
        """Ask Wikipedia what this probably means. Returns (titles, how)."""
        # Prefix and typo correction: "Ubood Bali" -> "Ubud, Bali".
        try:
            resp = self._session.get(WIKI_API, timeout=self._timeout, params={
                'action': 'opensearch', 'search': query, 'limit': 3, 'format': 'json'})
            if resp.status_code == 200:
                titles = resp.json()[1]
                if titles:
                    return titles, 'spelling'
        except (requests.RequestException, ValueError, IndexError) as exc:
            logger.debug('opensearch failed: %s', exc)

        # Descriptions: "the town with the rice terraces in Bali" -> "Tegallalang".
        try:
            resp = self._session.get(WIKI_API, timeout=self._timeout, params={
                'action': 'query', 'list': 'search', 'srsearch': query,
                'format': 'json', 'srlimit': 3})
            if resp.status_code == 200:
                hits = (resp.json().get('query') or {}).get('search') or []
                titles = [h['title'] for h in hits]
                if titles:
                    return titles, 'description'
        except (requests.RequestException, ValueError) as exc:
            logger.debug('wiki search failed: %s', exc)

        return [], 'none'

    def _geocode(self, query: str) -> Optional[Dict[str, Any]]:
        try:
            resp = self._session.get(NOMINATIM, timeout=self._timeout, params={
                'q': query, 'format': 'json', 'limit': 1, 'addressdetails': 1,
                'accept-language': 'en'})
        except requests.RequestException:
            return None
        if resp.status_code != 200:
            return None
        hits = resp.json()
        if not hits:
            return None
        hit = hits[0]
        return {
            'display_name': hit.get('display_name', query),
            'lat': float(hit['lat']),
            'lon': float(hit['lon']),
            'country': (hit.get('address') or {}).get('country', ''),
        }

    # ── general search ───────────────────────────────────────────

    def _provider(self) -> Optional[Tuple[str, str, str]]:
        for name, env, url in SEARCH_PROVIDERS:
            key = os.getenv(env)
            if key:
                return name, key, url
        return None

    @property
    def search_configured(self) -> bool:
        return self._provider() is not None

    def web_search(self, params: Dict[str, Any]) -> ToolResult:
        query = (params.get('query') or '').strip()
        if not query:
            return ToolResult(status=ToolStatus.ERROR, message='query is required',
                              error='Missing query')
        count = min(int(params.get('count', 5) or 5), 10)

        provider = self._provider()
        if provider is None:
            names = ', '.join(env for _, env, _ in SEARCH_PROVIDERS)
            prov = Provenance('websearch', SourceStatus.NOT_CONFIGURED,
                              detail=f'no search provider key set (one of: {names})')
            return ToolResult(
                status=ToolStatus.ERROR,
                data={'results': [], 'provenance': prov.to_dict()},
                message=('I cannot search the web — no search provider is configured. '
                         'Set BRAVE_SEARCH_API_KEY (free tier: 2,000 queries a month) '
                         'or TAVILY_API_KEY to enable it.'),
                error='no search provider',
            )

        name, key, url = provider
        try:
            if name == 'brave':
                resp = self._session.get(url, timeout=self._timeout,
                                         headers={'X-Subscription-Token': key,
                                                  'Accept': 'application/json'},
                                         params={'q': query, 'count': count})
                payload = resp.json() if resp.status_code == 200 else {}
                raw = (payload.get('web') or {}).get('results') or []
                results = [{'title': r.get('title'), 'url': r.get('url'),
                            'snippet': r.get('description')} for r in raw[:count]]
            else:  # tavily
                resp = self._session.post(url, timeout=self._timeout, json={
                    'api_key': key, 'query': query, 'max_results': count})
                payload = resp.json() if resp.status_code == 200 else {}
                results = [{'title': r.get('title'), 'url': r.get('url'),
                            'snippet': r.get('content')}
                           for r in (payload.get('results') or [])[:count]]
        except requests.RequestException as exc:
            prov = Provenance('websearch', SourceStatus.FAILED, url=url, detail=str(exc)[:160])
            return ToolResult(status=ToolStatus.ERROR,
                              data={'results': [], 'provenance': prov.to_dict()},
                              message=f'The web search failed: {exc}', error=str(exc))

        if resp.status_code != 200:
            prov = Provenance('websearch', SourceStatus.FAILED, url=url,
                              detail=f'HTTP {resp.status_code}: {resp.text[:140]}')
            return ToolResult(status=ToolStatus.ERROR,
                              data={'results': [], 'provenance': prov.to_dict()},
                              message=f'{name} returned HTTP {resp.status_code}',
                              error=f'HTTP {resp.status_code}')

        if not results:
            prov = Provenance('websearch', SourceStatus.UNAVAILABLE, url=url,
                              detail=f'no results for {query!r}')
            return ToolResult(status=ToolStatus.NO_RESULTS,
                              data={'results': [], 'provenance': prov.to_dict()},
                              message=f'The web had nothing for {query!r}')

        prov = Provenance('websearch', SourceStatus.LIVE, url=url,
                          attribution=f'Web results via {name}')
        return ToolResult(status=ToolStatus.SUCCESS,
                          data={'query': query, 'results': results,
                                'count': len(results), 'provider': name,
                                'provenance': prov.to_dict()},
                          message=f'{len(results)} web results via {name}')
