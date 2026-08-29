"""Provenance — every fact the agent shows must name where it came from.

The rule this module enforces: a record without a Provenance is not
displayable. There is no 'simulated' source. When a provider fails we emit a
Provenance with a failure status and NO data, never invented data with a
confident shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class SourceStatus(str, Enum):
    """Outcome of asking one provider for one thing."""
    LIVE = 'live'                 # Fetched fresh from the provider just now
    CACHED = 'cached'             # From our cache, still within TTL
    UNAVAILABLE = 'unavailable'   # Provider reachable but had no answer
    NOT_CONFIGURED = 'not_configured'  # No API key / provider disabled
    FAILED = 'failed'             # Provider errored, timed out, or refused


# Which real-world service each source id speaks to, for the UI badge.
SOURCE_LABELS = {
    'osm':        'OpenStreetMap',
    'nominatim':  'OpenStreetMap Nominatim',
    'wikipedia':  'Wikipedia',
    'wikimedia':  'Wikimedia Commons',
    'screenshot': 'Live screenshot',
    'osm_tiles':  'OpenStreetMap tiles',
    'atlas_cli':  'Atlas CLI',
    'aviationstack': 'AviationStack',
    'liteapi':    'LiteAPI',
    'booking_rapidapi': 'Booking.com (RapidAPI)',
    'openai':     'OpenAI',
    'ip-api':     'ip-api.com',
    'builtin':    'Bundled airport reference',
}


@dataclass
class Provenance:
    """Where a single piece of data came from, and how much to trust it."""
    source: str                              # id from SOURCE_LABELS
    status: SourceStatus = SourceStatus.LIVE
    url: str = ''                            # Exact endpoint or page hit
    fetched_at: str = ''                     # ISO8601 UTC
    license: str = ''                        # e.g. 'ODbL', 'CC BY-SA 4.0'
    detail: str = ''                         # Human note, esp. on failure
    attribution: str = ''                    # Text the UI must display

    def __post_init__(self):
        if not self.fetched_at:
            self.fetched_at = datetime.now(timezone.utc).isoformat()

    @property
    def label(self) -> str:
        return SOURCE_LABELS.get(self.source, self.source)

    @property
    def is_real(self) -> bool:
        """True only when this represents data actually returned by a provider."""
        return self.status in (SourceStatus.LIVE, SourceStatus.CACHED)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'source': self.source,
            'label': self.label,
            'status': self.status.value,
            'url': self.url,
            'fetched_at': self.fetched_at,
            'license': self.license,
            'detail': self.detail,
            'attribution': self.attribution,
            'is_real': self.is_real,
        }


@dataclass
class SourceReport:
    """What every provider did during one agent run.

    This is what makes degradation honest: the UI can say
    'prices unavailable — LiteAPI not configured' instead of showing a number
    nobody can stand behind.
    """
    entries: List[Provenance] = field(default_factory=list)

    def add(self, prov: Provenance) -> Provenance:
        self.entries.append(prov)
        return prov

    def note(self, source: str, status: SourceStatus, detail: str = '', url: str = '') -> Provenance:
        return self.add(Provenance(source=source, status=status, detail=detail, url=url))

    @property
    def failures(self) -> List[Provenance]:
        return [e for e in self.entries if not e.is_real]

    def missing_capabilities(self) -> List[str]:
        """Plain-language list of what the agent could NOT find out."""
        out = []
        for e in self.failures:
            if e.status == SourceStatus.NOT_CONFIGURED:
                out.append(f"{e.label} is not configured — {e.detail}" if e.detail
                           else f"{e.label} is not configured")
            elif e.status == SourceStatus.FAILED:
                out.append(f"{e.label} failed — {e.detail or 'no detail'}")
            elif e.status == SourceStatus.UNAVAILABLE:
                out.append(f"{e.label} had no data — {e.detail}" if e.detail
                           else f"{e.label} had no data")
        return out

    def attributions(self) -> List[str]:
        """Deduplicated attribution strings the UI is required to render."""
        seen, out = set(), []
        for e in self.entries:
            if e.attribution and e.attribution not in seen:
                seen.add(e.attribution)
                out.append(e.attribution)
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            'sources': [e.to_dict() for e in self.entries],
            'failures': [e.to_dict() for e in self.failures],
            'missing': self.missing_capabilities(),
            'attributions': self.attributions(),
        }


def stamp(record: Dict[str, Any], prov: Provenance) -> Dict[str, Any]:
    """Attach provenance to a record in place and return it."""
    record['provenance'] = prov.to_dict()
    record['source'] = prov.source
    return record
