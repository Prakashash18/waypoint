"""TripAgent — an LLM that plans trips by choosing its own tools.

This replaces the fixed pipeline in TripComposer, which always ran the same
two searches in the same order and assembled three packages by hardcoded rule.
Here the model decides what to look up, reads what came back, and follows up —
so "somewhere quiet near Ubud with a pool under $150" becomes a different
sequence of calls than "cheapest week in Bangkok".

Two invariants make the output trustworthy:

  1. Every fact the agent states must come from a tool result. The agent has no
     hotel knowledge of its own it is allowed to use.
  2. When a tool fails, the agent reports the gap. It never fills it in.

The full sequence of calls is recorded in `trace` so the UI can show exactly
what was consulted, and `sources` lists every provider with its status.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional

from ..tools import ToolResult, ToolStatus, tool_registry
from ..tools.provenance import Provenance, SourceReport, SourceStatus
from .api_tracker import tracker

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv('WAYPOINT_AGENT_MODEL', 'gpt-4o')
MAX_STEPS = 12

SYSTEM_PROMPT = """You are Waypoint, a travel agent that only tells the truth about real places.

You plan trips by calling tools. You have no independent knowledge of hotels,
prices, or availability that you are permitted to use — if a tool did not
return it, you do not know it.

ABSOLUTE RULES
1. Never invent a hotel name, price, rating, address, or photo. Not as an
   example, not as a placeholder, not "approximately".
2. If a tool fails or returns nothing, say so plainly and name what is missing.
   A shorter honest answer beats a complete-looking invented one.
3. Never state a nightly rate unless hotel_rates returned it. `places` hotels
   have NO prices — describing one, say the price is not available.
4. Only reference an image the imagery tool actually captured.

HOW TO WORK
- Resolve dates before searching. Today is {today}. Convert relative dates
  ("next month", "in 3 weeks") to YYYY-MM-DD yourself.
- For prices and bookable stays use `hotel_rates__search_hotels`.
- `places__find_hotels` gives real OpenStreetMap hotels with coordinates and
  official websites but no prices. Use it to go deeper on a specific area,
  to find places rates coverage missed, or when rates are unavailable.
- `places__describe_area` gives factual Wikipedia context about a neighbourhood.
- `imagery__capture_hotel_view` takes a live screenshot of a hotel's own
  website, or renders its exact coordinates on a map. Call it for your top
  recommendations so the traveller can see the real place. Pass the website and
  lat/lon you got from an earlier tool result.
- `atlas_flights__search_flights` needs IATA codes and returns real bookable
  flights. Airport codes are yours to resolve (Bali is DPS, Singapore is SIN).
- Search wide, then narrow. If the first result set misses the brief, adjust
  the parameters and search again rather than settling.

FINISHING
When you have enough, write the recommendation for the traveller. For each pick
give the real name, the real price with its currency (or "price not available"),
the real review score, and one concrete reason it fits what they asked. End with
a short line naming any source that failed, if any did."""


@dataclass
class TraceStep:
    """One thing the agent did, for the honesty panel in the UI."""
    step: int
    kind: str                       # 'tool_call' | 'message' | 'error'
    tool: str = ''
    capability: str = ''
    params: Dict[str, Any] = field(default_factory=dict)
    status: str = ''
    summary: str = ''
    duration_ms: int = 0
    result_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'step': self.step, 'kind': self.kind, 'tool': self.tool,
            'capability': self.capability, 'params': self.params,
            'status': self.status, 'summary': self.summary,
            'duration_ms': self.duration_ms, 'result_count': self.result_count,
        }


class TripAgent:
    """Tool-calling trip planner."""

    def __init__(self, registry=None, model: str = DEFAULT_MODEL,
                 max_steps: int = MAX_STEPS, api_key: Optional[str] = None):
        self.registry = registry or tool_registry
        self.model = model
        self.max_steps = max_steps
        self._api_key = api_key or os.getenv('OPENAI_API_KEY', '')

    # ── tool schema ──────────────────────────────────────────────

    def openai_tools(self) -> List[Dict[str, Any]]:
        """Expose every registered capability as an OpenAI function."""
        specs = []
        for tool in self.registry.list_tools():
            for cap in tool.capabilities:
                properties = {
                    pname: {'type': 'string', 'description': pdesc}
                    for pname, pdesc in (cap.parameters or {}).items()
                }
                specs.append({
                    'type': 'function',
                    'function': {
                        'name': f'{tool.name}__{cap.name}',
                        'description': f'[{tool.description}] {cap.description}',
                        'parameters': {
                            'type': 'object',
                            'properties': properties,
                            # The model is told which are required in the
                            # description; keeping this open lets it omit
                            # optional filters entirely.
                            'required': [],
                        },
                    },
                })
        return specs

    # ── main loop ────────────────────────────────────────────────

    def plan(self, request: str, context: Optional[Dict[str, Any]] = None,
             on_step: Optional[Callable[[TraceStep], None]] = None) -> Dict[str, Any]:
        """Plan a trip from a natural-language request.

        Args:
            request: What the traveller asked for, in their own words.
            context: Optional known facts (origin, dates, budget, party size).
            on_step: Called after each trace step, for live streaming.

        Returns a dict with the answer, the trace, collected artifacts and
        a source report naming every provider consulted.
        """
        started = time.time()
        trace: List[TraceStep] = []
        sources = SourceReport()
        artifacts: Dict[str, List[Dict[str, Any]]] = {
            'hotels': [], 'flights': [], 'images': [], 'areas': [],
        }

        if not self._api_key:
            return self._no_llm(request, sources, started)

        import openai
        client = openai.OpenAI(api_key=self._api_key)

        system = SYSTEM_PROMPT.format(today=date.today().isoformat())
        if context:
            system += f"\n\nKnown so far: {json.dumps(context, default=str)}"

        messages: List[Dict[str, Any]] = [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': request},
        ]
        tools = self.openai_tools()
        answer = ''
        stopped = 'completed'

        for step in range(1, self.max_steps + 1):
            t0 = time.time()
            try:
                response = client.chat.completions.create(
                    model=self.model, messages=messages,
                    tools=tools, tool_choice='auto', temperature=0.2,
                )
            except Exception as exc:
                logger.exception('Agent LLM call failed')
                s = TraceStep(step=step, kind='error', status='error',
                              summary=f'{type(exc).__name__}: {exc}',
                              duration_ms=int((time.time() - t0) * 1000))
                trace.append(s)
                if on_step:
                    on_step(s)
                sources.note('openai', SourceStatus.FAILED, detail=str(exc)[:200])
                stopped = 'llm_error'
                answer = (f'I could not finish planning — the reasoning model failed '
                          f'({type(exc).__name__}). Nothing below is invented; '
                          f'I simply stopped early.')
                break

            self._track(response, int((time.time() - t0) * 1000))
            choice = response.choices[0].message
            messages.append(choice.model_dump(exclude_none=True))

            if not choice.tool_calls:
                answer = choice.content or ''
                s = TraceStep(step=step, kind='message', status='final',
                              summary=answer[:200],
                              duration_ms=int((time.time() - t0) * 1000))
                trace.append(s)
                if on_step:
                    on_step(s)
                break

            for call in choice.tool_calls:
                result_msg, s = self._run_tool(call, step, artifacts, sources)
                trace.append(s)
                if on_step:
                    on_step(s)
                messages.append(result_msg)
        else:
            stopped = 'max_steps'
            answer = answer or ('I ran out of planning steps before finishing. '
                                'What I found so far is below — none of it is invented.')

        return {
            'request': request,
            'answer': answer,
            'trace': [s.to_dict() for s in trace],
            'artifacts': artifacts,
            'sources': sources.to_dict(),
            'tool_calls': sum(1 for s in trace if s.kind == 'tool_call'),
            'steps': len(trace),
            'stopped': stopped,
            'duration_ms': int((time.time() - started) * 1000),
            'model': self.model,
        }

    # ── tool execution ───────────────────────────────────────────

    def _run_tool(self, call, step: int, artifacts: Dict[str, List],
                  sources: SourceReport):
        """Execute one tool call and produce both the model message and a trace step."""
        name = call.function.name
        tool_name, _, capability = name.partition('__')
        t0 = time.time()

        try:
            params = json.loads(call.function.arguments or '{}')
        except json.JSONDecodeError:
            params = {}
        params = self._coerce(params)

        try:
            result: ToolResult = self.registry.execute(tool_name, capability, params)
        except Exception as exc:
            logger.warning('Tool %s failed: %s', name, exc)
            sources.note(tool_name, SourceStatus.FAILED, detail=f'{type(exc).__name__}: {exc}')
            payload = {'status': 'error',
                       'message': f'{type(exc).__name__}: {exc}',
                       'instruction': 'This tool failed. Do not invent a substitute result.'}
            s = TraceStep(step=step, kind='tool_call', tool=tool_name, capability=capability,
                          params=params, status='error', summary=str(exc)[:200],
                          duration_ms=int((time.time() - t0) * 1000))
            return self._tool_message(call.id, payload), s

        self._collect(tool_name, capability, result, artifacts, sources)
        payload = self._summarize(result)
        count = payload.get('count', 0) or 0

        s = TraceStep(step=step, kind='tool_call', tool=tool_name, capability=capability,
                      params=params, status=result.status.value,
                      summary=result.message[:220], result_count=count,
                      duration_ms=int((time.time() - t0) * 1000))
        return self._tool_message(call.id, payload), s

    @staticmethod
    def _tool_message(call_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {'role': 'tool', 'tool_call_id': call_id,
                'content': json.dumps(payload, default=str)[:14000]}

    @staticmethod
    def _coerce(params: Dict[str, Any]) -> Dict[str, Any]:
        """The function schema declares strings; tools want numbers for some fields."""
        numeric = {'adults', 'children', 'rooms', 'limit', 'radius_m', 'min_stars',
                   'max_price', 'min_review_score', 'lat', 'lon', 'budget'}
        out = {}
        for key, value in params.items():
            if key in numeric and isinstance(value, str) and value.strip():
                try:
                    out[key] = float(value) if '.' in value else int(value)
                    continue
                except ValueError:
                    pass
            out[key] = value
        return out

    def _collect(self, tool_name: str, capability: str, result: ToolResult,
                 artifacts: Dict[str, List], sources: SourceReport) -> None:
        """Keep the full records for the UI, and record what each provider did."""
        data = result.data if isinstance(result.data, dict) else {}

        prov_dict = data.get('provenance')
        if prov_dict:
            sources.add(Provenance(
                source=prov_dict.get('source', tool_name),
                status=SourceStatus(prov_dict.get('status', 'live')),
                url=prov_dict.get('url', ''), license=prov_dict.get('license', ''),
                detail=prov_dict.get('detail', ''),
                attribution=prov_dict.get('attribution', ''),
            ))
        elif result.is_error():
            sources.note(tool_name, SourceStatus.FAILED, detail=result.message[:200])

        if capability in ('search_hotels', 'find_hotels'):
            self._merge_hotels(artifacts['hotels'], data.get('hotels') or [])
        elif capability == 'search_flights':
            artifacts['flights'] = data.get('offers') or artifacts['flights']
        elif capability == 'capture_hotel_view' and data.get('image_url'):
            artifacts['images'].append(data)
        elif capability == 'find_photos':
            artifacts['images'].extend(data.get('photos') or [])
        elif capability == 'describe_area' and data.get('summary'):
            artifacts['areas'].append(data)

    @staticmethod
    def _merge_hotels(existing: List[Dict], incoming: List[Dict]) -> None:
        """Same hotel from two providers should be one card, priced if either had a price."""
        by_name = {h['name'].strip().lower(): h for h in existing if h.get('name')}
        for hotel in incoming:
            key = (hotel.get('name') or '').strip().lower()
            if not key:
                continue
            current = by_name.get(key)
            if not current:
                existing.append(hotel)
                by_name[key] = hotel
                continue
            # Fill gaps only — never overwrite a real value with a null.
            for field_name, value in hotel.items():
                if value not in (None, '', []) and current.get(field_name) in (None, '', []):
                    current[field_name] = value

    @staticmethod
    def _summarize(result: ToolResult) -> Dict[str, Any]:
        """Trim a tool result to what the model needs to reason, to control tokens."""
        payload: Dict[str, Any] = {'status': result.status.value, 'message': result.message}
        data = result.data if isinstance(result.data, dict) else {}

        if result.is_error() or result.status == ToolStatus.NO_RESULTS:
            prov = data.get('provenance') or {}
            payload['reason'] = prov.get('detail') or result.error or result.message
            payload['instruction'] = (
                'This source gave no data. Tell the user this specific thing is '
                'unavailable. Do NOT substitute invented values.')
            return payload

        hotels = data.get('hotels')
        if hotels is not None:
            payload['count'] = len(hotels)
            payload['has_prices'] = data.get('has_prices', False)
            payload['hotels'] = [{
                k: h.get(k) for k in (
                    'hotel_id', 'name', 'area', 'stars', 'review_score', 'review_count',
                    'total_price', 'price_per_night', 'currency', 'lat', 'lon',
                    'website', 'distance_km', 'amenities', 'address')
                if h.get(k) not in (None, '', [])
            } for h in hotels[:15]]
            if not data.get('has_prices', False):
                payload['price_note'] = ('These hotels are real but have NO price data. '
                                         'Do not state a rate for them.')
            return payload

        offers = data.get('offers')
        if offers is not None:
            payload['count'] = len(offers)
            payload['offers'] = [{
                k: o.get(k) for k in ('offer_id', 'price', 'currency', 'airline',
                                      'flight_number', 'departure_time', 'arrival_time',
                                      'duration_minutes', 'stops')
                if o.get(k) is not None
            } for o in offers[:12]]
            return payload

        photos = data.get('photos')
        if photos is not None:
            payload['count'] = len(photos)
            payload['photos'] = [
                {'title': p.get('title'), 'url': p.get('url')} if isinstance(p, dict)
                else {'url': p} for p in photos[:6]
            ]
            return payload

        if data.get('image_url') or 'attempts' in data:
            payload['count'] = 1 if data.get('image_url') else 0
            payload['image_url'] = data.get('image_url')
            payload['capture_mode'] = data.get('capture_mode')
            payload['attempts'] = data.get('attempts')
            return payload

        payload['data'] = {k: v for k, v in data.items() if k != 'provenance'}
        payload['count'] = 1
        return payload

    @staticmethod
    def _track(response, duration_ms: int) -> None:
        usage = getattr(response, 'usage', None)
        if not usage:
            return
        try:
            tracker.record_openai(
                model=response.model,
                tokens_in=usage.prompt_tokens, tokens_out=usage.completion_tokens,
                endpoint='trip_agent', duration_ms=duration_ms,
            )
        except Exception as exc:
            logger.debug('tracker failed: %s', exc)

    def _no_llm(self, request: str, sources: SourceReport, started: float) -> Dict[str, Any]:
        sources.note('openai', SourceStatus.NOT_CONFIGURED,
                     detail='OPENAI_API_KEY is not set, so the agent cannot plan')
        return {
            'request': request,
            'answer': ('I cannot plan this trip: OPENAI_API_KEY is not set, so the '
                       'planning model is unavailable. I will not guess at an itinerary.'),
            'trace': [], 'artifacts': {'hotels': [], 'flights': [], 'images': [], 'areas': []},
            'sources': sources.to_dict(), 'tool_calls': 0, 'steps': 0,
            'stopped': 'not_configured',
            'duration_ms': int((time.time() - started) * 1000), 'model': self.model,
        }
