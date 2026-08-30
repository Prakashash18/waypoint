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
from .session import Session
from ..tools.provenance import Provenance, SourceReport, SourceStatus
from .api_tracker import tracker

logger = logging.getLogger(__name__)


def _clean_image_refs(answer: str) -> str:
    """Models sometimes prefix local image paths with 'sandbox:'; strip it."""
    import re
    return re.sub(r'\(sandbox:(/static/)', r'(\1', answer or '')

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

MONEY AND TIME — READ THIS BEFORE QUOTING ANYTHING
- `price_total` on a flight offer is the fare for EVERYONE on the booking.
  `price_per_passenger` is the per-person fare. Say which one you mean. Calling
  a two-adult total a per-person price doubles the trip in the traveller's head.
- A hotel's `total_price` covers the WHOLE STAY, not one night;
  `price_per_night` is the nightly rate. Never report a total as a nightly rate:
  a four-night total read as per-night quadruples the stay.
- Quote in the traveller's own currency when one is known (see below), and name
  the currency. Never convert between currencies yourself — you have no rate.
  If a price came back in a different currency, say so plainly.
- Flight times are LOCAL TO EACH AIRPORT, which is how airlines publish them.
  When the traveller's timezone differs from the departure airport's, say so
  rather than silently implying their own clock.

WHERE THE TRAVELLER IS
- Do not assume a home airport. If you have not been told where they are,
  call `locale__detect_locale` first, then `places__nearest_airports` with the
  coordinates it returns, and fly them from the nearest sensible airport.
- Say which airport you chose and why, so they can correct it in one sentence.

HOW TO WORK
- Resolve dates before searching. Today is {today}. Convert relative dates
  ("next month", "in 3 weeks") to YYYY-MM-DD yourself.
- NO DATES GIVEN, or the traveller says "whenever is cheapest" / "sometime in
  October" / "if we shifted a few days": use `atlas_flights__find_date_deals`,
  which prices several windows and returns them cheapest first. Do not invent
  a date and search once — the whole question was which date to pick.
- For prices and bookable stays use `hotel_rates__search_hotels`.
- `places__find_hotels` gives real OpenStreetMap hotels with coordinates and
  official websites but no prices. Use it to go deeper on a specific area,
  to find places rates coverage missed, or when rates are unavailable.
- `places__describe_area` gives factual Wikipedia context about a neighbourhood.

SHOWING THE TRAVELLER WHAT A PLACE LOOKS LIKE
- Hotels from `hotel_rates` already carry real Booking.com photographs in
  `image_url`. Those are real; reference them directly and do not re-capture.
- For a screenshot of the hotel's OWN website, the rate result has no website
  field. Call `places__match_hotel` with the hotel's name and lat/lon to
  recover the official site, then pass that website to
  `imagery__capture_hotel_view`. Do this for your single top pick.
- If no website is found, call `imagery__capture_hotel_view` with just lat/lon
  to render the exact location on a map.
- Reference any captured image by the exact `image_url` string the tool
  returned, with no prefix added.
- `atlas_flights__search_flights` needs IATA codes and returns real bookable
  flights. Airport codes are yours to resolve (Bali is DPS, Singapore is SIN).
- Search wide, then narrow. If the first result set misses the brief, adjust
  the parameters and search again rather than settling.

WHEN SOMETHING IS MISSING
- If a tool reports missing parameters, you left them out. Work out the values
  and call it again — resolve the airport with places__nearest_airports, the
  dates from what the traveller said, the destination from their words.
- If a value is genuinely something only the traveller can tell you (where they
  want to go, how long, how many people), ASK THEM ONE SHORT QUESTION and stop.
  Do not report that a tool failed, and do not guess. "Which dates did you have
  in mind?" is a good answer. "I could not retrieve that information" is not.

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
                 max_steps: int = MAX_STEPS, api_key: Optional[str] = None,
                 request_timeout: float = 90.0):
        self.registry = registry or tool_registry
        self.model = model
        self.max_steps = max_steps
        self.request_timeout = request_timeout
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
                            # Only the genuinely mandatory ones. Declaring
                            # nothing required let the model call a tool with
                            # no arguments and then tell the traveller it could
                            # not retrieve anything.
                            'required': [r for r in cap.required if r in properties],
                        },
                    },
                })
        return specs

    # ── main loop ────────────────────────────────────────────────

    def plan(self, request: str, context: Optional[Dict[str, Any]] = None,
             on_step: Optional[Callable[[TraceStep], None]] = None,
             session: Optional[Session] = None) -> Dict[str, Any]:
        """Plan a trip from a natural-language request.

        Args:
            request: What the traveller asked for, in their own words.
            context: Optional known facts (origin, dates, budget, party size).
            on_step: Called after each trace step, for live streaming.
            session: Carries the conversation forward. With one, a follow-up
                like "compare the top two" continues from what the last run
                found instead of searching again from nothing.

        Returns a dict with the answer, the trace, collected artifacts and
        a source report naming every provider consulted.
        """
        started = time.time()
        trace: List[TraceStep] = []
        sources = SourceReport()

        # Carry forward what the last run found, so a follow-up can talk about
        # those hotels without re-fetching them.
        prior = dict(session.artifacts) if session else {}

        # Sessions live in memory, so a restart or a sleeping instance loses
        # them while the traveller is still looking at the results. The client
        # sends back what is on their screen; trust it to re-seed rather than
        # answering a follow-up as though nothing had ever been found.
        if not prior.get('hotels') and not prior.get('flights'):
            seen = (context or {}).get('seen') or {}
            if seen.get('hotels') or seen.get('flight'):
                prior = {
                    'hotels': seen.get('hotels') or [],
                    'flights': [seen['flight']] if seen.get('flight') else [],
                    'windows': seen.get('windows') or [],
                    'locale': seen.get('locale'),
                    'images': [], 'areas': [], 'airports': [],
                }
                logger.info('Re-seeded %d hotels from what the client had on screen',
                            len(prior['hotels']))
        artifacts: Dict[str, Any] = {
            'hotels': list(prior.get('hotels') or []),
            'flights': list(prior.get('flights') or []),
            'images': list(prior.get('images') or []),
            'areas': list(prior.get('areas') or []),
            'windows': list(prior.get('windows') or []),
            'airports': list(prior.get('airports') or []),
            'locale': prior.get('locale'),
        }
        if session:
            session.clear_cancel()
            session.running = True

        if not self._api_key:
            return self._no_llm(request, sources, started)

        import openai
        client = openai.OpenAI(api_key=self._api_key)

        system = SYSTEM_PROMPT.format(today=date.today().isoformat())

        locale = self._resolve_locale(context, artifacts, sources)
        if locale:
            where = ', '.join(filter(None, [locale.get('city'), locale.get('country')]))
            system += (
                f"\n\nTHE TRAVELLER IS IN {where or 'an unknown place'}"
                f" (detected from their {locale.get('source', 'ip')})."
                f"\n- Quote prices in {locale['currency']}"
                f" (symbol {locale.get('currency_symbol', '')})."
                f" Pass currency={locale['currency']} to every search."
                f"\n- Their timezone is {locale.get('timezone') or 'unknown'}"
                f" {locale.get('utc_offset_label', '')}."
                f"\n- Their coordinates are {locale.get('lat')}, {locale.get('lon')} —"
                f" use places__nearest_airports on these to pick a departure airport"
                f" unless they named one."
            )
        if session and session.preferences:
            system += ("\n\nWHAT THIS TRAVELLER HAS TOLD YOU BEFORE\n"
                       + json.dumps(session.preferences, default=str)
                       + "\nApply these unless this request overrides them, and do not "
                         "ask again for something already listed here.")

        carried = self._describe_carried(artifacts)
        if carried:
            system += ("\n\nALREADY FOUND EARLIER IN THIS CONVERSATION\n" + carried +
                       "\nWhen the traveller refers to these ('the top two', 'the second "
                       "one', 'that hotel'), answer from them directly. Search again only "
                       "if they ask for something genuinely new.")

        if context:
            system += f"\n\nKnown so far: {json.dumps(context, default=str)}"

        history = [m for m in (session.messages if session else []) if m.get('role') != 'system']
        messages: List[Dict[str, Any]] = [
            {'role': 'system', 'content': system},
            *history,
            {'role': 'user', 'content': request},
        ]
        tools = self.openai_tools()
        answer = ''
        stopped = 'completed'

        for step in range(1, self.max_steps + 1):
            if session and session.cancelled:
                stopped = 'cancelled'
                answer = answer or 'Stopped. Nothing below is invented — it is what I had found so far.'
                break
            t0 = time.time()
            try:
                response = client.chat.completions.create(
                    model=self.model, messages=messages,
                    tools=tools, tool_choice='auto', temperature=0.2,
                    # Without a cap the final write-up can run for minutes on a
                    # large result set; a recommendation does not need more.
                    max_tokens=1100,
                    timeout=self.request_timeout,
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
                if session and session.cancelled:
                    # The model expects a result for every call it made, so
                    # answer the outstanding ones rather than leaving a gap.
                    messages.append(self._tool_message(
                        call.id, {'status': 'cancelled',
                                  'message': 'the traveller interrupted'}))
                    continue
                result_msg, s = self._run_tool(call, step, artifacts, sources)
                trace.append(s)
                if on_step:
                    on_step(s)
                messages.append(result_msg)
        else:
            stopped = 'max_steps'
            answer = answer or ('I ran out of planning steps before finishing. '
                                'What I found so far is below — none of it is invented.')

        # The model is not reliable about always fetching an image, and it once
        # claimed no picture existed for a hotel that had one. Imagery is a
        # guarantee of this system, not a decision left to the model: every
        # hotel it actually recommended gets a real image or an explicit reason
        # there is none.
        self._ensure_imagery(answer, artifacts, sources, trace, on_step)
        answer = _clean_image_refs(answer)

        if session:
            session.running = False
            session.artifacts = artifacts
            if artifacts.get('locale'):
                session.locale = artifacts['locale']
            # Keep only the plain turns: replaying tool payloads would bloat
            # every later request for little benefit.
            session.messages = [
                m for m in messages
                if m.get('role') in ('user', 'assistant')
                and m.get('content') and not m.get('tool_calls')
            ]
            session.trim()

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
            'session_id': session.id if session else None,
            'preferences': dict(session.preferences) if session else {},
        }

    @staticmethod
    def _describe_carried(artifacts: Dict[str, Any]) -> str:
        """A compact index of prior results, for the model to refer back to."""
        lines = []
        hotels = artifacts.get('hotels') or []
        for i, h in enumerate(hotels[:8], 1):
            if h.get('total_price') is not None:
                nights = h.get('nights')
                per = h.get('price_per_night')
                price = (f"{h.get('currency','')} {h['total_price']:.2f} TOTAL"
                         + (f" for {nights} nights" if nights else '')
                         + (f" ({h.get('currency','')} {per:.2f} per night)" if per else ''))
            else:
                price = 'no price available'
            score = (f", rated {h['review_score']}/10" if h.get('review_score')
                     else ', no reviews yet')
            lines.append(f"  hotel {i}: {h.get('name')} — {price}{score}"
                         f" (hotel_id {h.get('hotel_id','?')})")
        flights = artifacts.get('flights') or []
        for f in flights[:3]:
            lines.append(f"  flight: {f.get('flight_code')} {f.get('origin')}→"
                         f"{f.get('destination')} {f.get('currency','')} "
                         f"{f.get('price_total')} for {f.get('passengers')} "
                         f"(offer_id {f.get('offer_id','?')})")
        windows = artifacts.get('windows') or []
        if windows:
            best = min(windows, key=lambda w: w.get('price_total', 1e9))
            lines.append(f"  {len(windows)} date windows priced; cheapest "
                         f"{best.get('depart')} at {best.get('currency','')} "
                         f"{best.get('price_total')}")
        return '\n'.join(lines)

    def _resolve_locale(self, context: Optional[Dict[str, Any]],
                        artifacts: Dict[str, Any],
                        sources: SourceReport) -> Optional[Dict[str, Any]]:
        """Find out where the traveller is before the model starts guessing.

        The old agent assumed Kuala Lumpur and quoted USD at everyone. Doing
        this once up front costs one call and removes both assumptions.
        """
        supplied = (context or {}).get('locale') or artifacts.get('locale')
        if isinstance(supplied, dict) and supplied.get('currency'):
            artifacts['locale'] = supplied
            return supplied

        params = {k: (context or {}).get(k) for k in ('lat', 'lon', 'timezone')}
        params = {k: v for k, v in params.items() if v is not None}
        try:
            result = self.registry.execute('locale', 'detect_locale', params)
        except Exception as exc:
            logger.warning('Locale detection failed: %s', exc)
            sources.note('locale', SourceStatus.FAILED, detail=str(exc)[:160])
            return None

        data = result.data if isinstance(result.data, dict) else {}
        prov = data.get('provenance')
        if prov:
            sources.add(Provenance(
                source=prov.get('source', 'locale'),
                status=SourceStatus(prov.get('status', 'live')),
                url=prov.get('url', ''), detail=prov.get('detail', ''),
                attribution=prov.get('attribution', '')))
        if result.is_success() and data.get('detected'):
            artifacts['locale'] = data
            return data
        return None

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
        elif capability == 'find_date_deals':
            artifacts['windows'] = data.get('windows') or artifacts['windows']
        elif capability == 'nearest_airports':
            artifacts['airports'] = data.get('airports') or artifacts['airports']
        elif capability == 'detect_locale' and data.get('detected'):
            artifacts['locale'] = data
        elif capability == 'match_hotel' and data.get('name'):
            self._merge_hotels(artifacts['hotels'], [data])
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
            } for h in hotels[:12]]
            if not data.get('has_prices', False):
                payload['price_note'] = ('These hotels are real but have NO price data. '
                                         'Do not state a rate for them.')
            return payload

        offers = data.get('offers')
        if offers is not None:
            payload['count'] = len(offers)
            payload['offers'] = [{
                k: o.get(k) for k in (
                    'offer_id', 'flight_code', 'airline', 'price_total',
                    'price_per_passenger', 'passengers', 'currency', 'origin',
                    'destination', 'departure_time', 'arrival_time',
                    'duration_minutes', 'stops', 'round_trip', 'return_leg')
                if o.get(k) is not None
            } for o in offers[:8]]
            payload['price_note'] = (
                'price_total covers ALL passengers on the booking; '
                'price_per_passenger is the per-person fare. Do not confuse them.')
            return payload

        windows = data.get('windows')
        if windows is not None:
            payload['count'] = len(windows)
            payload['windows'] = windows[:9]
            payload['cheapest'] = data.get('cheapest')
            payload['saving_vs_anchor'] = data.get('saving_vs_anchor')
            if data.get('unpriced_dates'):
                payload['unpriced_dates'] = data['unpriced_dates']
                payload['unpriced_note'] = ('No fare came back for these dates. Say they '
                                            'could not be checked; do not estimate them.')
            payload['price_note'] = 'Every price_total covers all passengers.'
            return payload

        airports = data.get('airports')
        if airports is not None:
            payload['count'] = len(airports)
            payload['airports'] = airports[:5]
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

    def _ensure_imagery(self, answer: str, artifacts: Dict[str, List],
                        sources: SourceReport, trace: List[TraceStep],
                        on_step: Optional[Callable] = None, limit: int = 3) -> None:
        """Guarantee a real image for every hotel the agent recommended.

        Order of preference, all of them real:
          1. the photograph the rate provider already returned
          2. a live screenshot of the hotel's own website (via OSM match)
          3. a map rendered on the hotel's exact coordinates
        A hotel that reaches the end with none of these is marked as having no
        image, which the UI shows as such.
        """
        hotels = artifacts.get('hotels') or []
        if not hotels:
            return

        # Labelling a photo the provider already returned costs nothing, so do
        # it for every hotel — otherwise cards past the top few look imageless.
        for hotel in hotels:
            if hotel.get('image_url') and not hotel.get('image_source'):
                hotel['image_source'] = 'provider_photo'

        lowered = (answer or '').lower()
        recommended = [h for h in hotels if h.get('name', '').lower() in lowered]
        if not recommended:
            recommended = hotels[:limit]
        recommended = recommended[:limit]

        step_no = (trace[-1].step if trace else 0) + 1

        for hotel in recommended:
            if hotel.get('image_url'):
                hotel['image_source'] = hotel.get('image_source') or 'provider_photo'
                continue

            website = hotel.get('website') or ''
            lat, lon = hotel.get('lat'), hotel.get('lon')

            # Recover the official website so we can screenshot the real site.
            if not website and lat is not None and lon is not None:
                match = self._safe_call('places', 'match_hotel', {
                    'name': hotel.get('name', ''), 'lat': lat, 'lon': lon,
                }, step_no, trace, sources, on_step)
                step_no += 1
                if match and match.is_success() and isinstance(match.data, dict):
                    website = match.data.get('website') or ''
                    for key in ('address', 'phone', 'osm_url', 'amenities'):
                        if match.data.get(key) and not hotel.get(key):
                            hotel[key] = match.data[key]
                    if website:
                        hotel['website'] = website

            shot = self._safe_call('imagery', 'capture_hotel_view', {
                'name': hotel.get('name', ''), 'website': website,
                'lat': lat, 'lon': lon,
                'prefer': 'website' if website else 'map',
            }, step_no, trace, sources, on_step)
            step_no += 1

            if shot and shot.is_success() and isinstance(shot.data, dict):
                hotel['image_url'] = shot.data.get('image_url')
                hotel['image_source'] = shot.data.get('capture_mode')
                hotel['image_provenance'] = shot.data.get('provenance')
                artifacts['images'].append(shot.data)
            else:
                hotel['image_url'] = None
                hotel['image_source'] = 'none'
                hotel['image_note'] = (
                    shot.message if shot else 'imagery tool unavailable')

    def _safe_call(self, tool: str, capability: str, params: Dict[str, Any],
                   step_no: int, trace: List[TraceStep], sources: SourceReport,
                   on_step: Optional[Callable]) -> Optional[ToolResult]:
        """Run a tool outside the model loop, still recording it in the trace."""
        t0 = time.time()
        try:
            result = self.registry.execute(tool, capability, params)
        except Exception as exc:
            logger.warning('Enrichment %s.%s failed: %s', tool, capability, exc)
            sources.note(tool, SourceStatus.FAILED, detail=str(exc)[:200])
            result = None

        step = TraceStep(
            step=step_no, kind='tool_call', tool=tool, capability=capability,
            params=params, status=result.status.value if result else 'error',
            summary=(result.message if result else 'tool raised')[:200],
            duration_ms=int((time.time() - t0) * 1000),
            result_count=1 if result and result.is_success() else 0,
        )
        step.summary = f'[auto] {step.summary}'
        trace.append(step)
        if on_step:
            on_step(step)

        if result is not None:
            data = result.data if isinstance(result.data, dict) else {}
            prov = data.get('provenance')
            if prov:
                sources.add(Provenance(
                    source=prov.get('source', tool),
                    status=SourceStatus(prov.get('status', 'live')),
                    url=prov.get('url', ''), license=prov.get('license', ''),
                    detail=prov.get('detail', ''),
                    attribution=prov.get('attribution', ''),
                ))
        return result

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
