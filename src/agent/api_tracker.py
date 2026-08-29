"""
API Call Tracker
Tracks usage across all external API calls for cost monitoring and rate limiting
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List
import threading
import json


@dataclass
class APICall:
    """Single API call record"""
    timestamp: datetime
    service: str       # openai, aviationstack, atlas_cli
    endpoint: str      # e.g. chat.completions, flights, search
    model: str = ""    # e.g. gpt-4, gpt-4-vision-preview
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    status: str = "success"  # success, error, fallback
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'service': self.service,
            'endpoint': self.endpoint,
            'model': self.model,
            'tokens_in': self.tokens_in,
            'tokens_out': self.tokens_out,
            'cost_usd': self.cost_usd,
            'status': self.status,
            'duration_ms': self.duration_ms,
        }


# Pricing per 1M tokens (USD) as of 2026
OPENAI_PRICING = {
    'gpt-4':           {'in': 30.00, 'out': 60.00},
    'gpt-4-turbo':     {'in': 10.00, 'out': 30.00},
    'gpt-4o':          {'in': 5.00,  'out': 15.00},
    'gpt-4-vision-preview': {'in': 30.00, 'out': 60.00},
    'gpt-3.5-turbo':   {'in': 0.50,  'out': 1.50},
}

AVIATIONSTACK_COST = 0.0  # Free tier, but limited to 100 req/month
AMADEUS_COST = 0.0  # Free sandbox tier
ELEVENLABS_COST_PER_CHAR = 0.0001  # 1 credit/char on free tier, 10K credits/month


class APICallTracker:
    """Thread-safe API call tracker"""

    def __init__(self):
        self._calls: List[APICall] = []
        self._lock = threading.Lock()

    # ── Recording ──────────────────────────────────────────────

    def record(self, call: APICall):
        """Record an API call"""
        with self._lock:
            self._calls.append(call)

    def record_openai(self, model: str, tokens_in: int, tokens_out: int,
                      endpoint: str = "chat.completions",
                      duration_ms: int = 0, status: str = "success"):
        """Record an OpenAI API call with cost calculation"""
        pricing = OPENAI_PRICING.get(model, {'in': 30.00, 'out': 60.00})
        cost = (tokens_in * pricing['in'] + tokens_out * pricing['out']) / 1_000_000

        self.record(APICall(
            timestamp=datetime.utcnow(),
            service='openai',
            endpoint=endpoint,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=round(cost, 6),
            status=status,
            duration_ms=duration_ms,
        ))

    def record_aviationstack(self, endpoint: str = "flights",
                             duration_ms: int = 0, status: str = "success"):
        """Record an AviationStack API call"""
        self.record(APICall(
            timestamp=datetime.utcnow(),
            service='aviationstack',
            endpoint=endpoint,
            cost_usd=AVIATIONSTACK_COST,
            status=status,
            duration_ms=duration_ms,
        ))

    def record_atlas_cli(self, endpoint: str, duration_ms: int = 0,
                         status: str = "success"):
        """Record an Atlas CLI invocation"""
        self.record(APICall(
            timestamp=datetime.utcnow(),
            service='atlas_cli',
            endpoint=endpoint,
            cost_usd=0.0,
            status=status,
            duration_ms=duration_ms,
        ))

    def record_amadeus(self, endpoint: str, duration_ms: int = 0,
                       status: str = "success"):
        """Record an Amadeus API call (free sandbox)"""
        self.record(APICall(
            timestamp=datetime.utcnow(),
            service='amadeus',
            endpoint=endpoint,
            cost_usd=AMADEUS_COST,
            status=status,
            duration_ms=duration_ms,
        ))

    def record_elevenlabs(self, endpoint: str, characters: int = 0,
                          duration_ms: int = 0, status: str = "success"):
        """Record an ElevenLabs TTS API call"""
        cost = characters * ELEVENLABS_COST_PER_CHAR
        self.record(APICall(
            timestamp=datetime.utcnow(),
            service='elevenlabs',
            endpoint=endpoint,
            cost_usd=round(cost, 6),
            status=status,
            duration_ms=duration_ms,
        ))

    # ── Queries ────────────────────────────────────────────────

    def summary(self) -> Dict:
        """Get summary of all API calls"""
        with self._lock:
            by_service: Dict[str, Dict] = {}
            total_cost = 0.0
            total_tokens_in = 0
            total_tokens_out = 0

            for call in self._calls:
                svc = call.service
                if svc not in by_service:
                    by_service[svc] = {'count': 0, 'cost_usd': 0.0, 'errors': 0}
                by_service[svc]['count'] += 1
                by_service[svc]['cost_usd'] += call.cost_usd
                if call.status == 'error':
                    by_service[svc]['errors'] += 1
                total_cost += call.cost_usd
                total_tokens_in += call.tokens_in
                total_tokens_out += call.tokens_out

            return {
                'total_calls': len(self._calls),
                'total_cost_usd': round(total_cost, 6),
                'total_tokens_in': total_tokens_in,
                'total_tokens_out': total_tokens_out,
                'by_service': by_service,
            }

    def recent(self, n: int = 20) -> List[dict]:
        """Get the N most recent calls"""
        with self._lock:
            return [c.to_dict() for c in self._calls[-n:]][::-1]

    def export_json(self) -> str:
        """Export full call log as JSON"""
        with self._lock:
            return json.dumps({
                'summary': self.summary(),
                'calls': [c.to_dict() for c in self._calls],
            }, indent=2)

    # ── Simulate Toggle ────────────────────────────────────────




# Singleton instance used across the application
tracker = APICallTracker()
