"""AtlasTool — wraps AtlasCLI for the tool registry.

Capabilities: search_flights, verify_offer, book_flight
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base import ToolBase, ToolCapability, ToolError, ToolResult, ToolStatus
from ..cli.wrapper import AtlasCLI
from ..cli.errors import AtlasError

logger = logging.getLogger(__name__)


class AtlasTool(ToolBase):
    """Flight search and booking via Atlas CLI."""
    
    def __init__(self, cli: Optional[AtlasCLI] = None):
        self._cli = cli or AtlasCLI()
    
    @property
    def name(self) -> str:
        return 'atlas_flights'
    
    @property
    def description(self) -> str:
        return 'Search and book flights via Atlas CLI'
    
    @property
    def capabilities(self) -> List[ToolCapability]:
        return [
            ToolCapability(
                name='search_flights',
                description='Search for one-way or round-trip flights',
                parameters={
                    'origin': 'IATA airport code (e.g. KUL)',
                    'destination': 'IATA airport code (e.g. SIN)',
                    'depart': 'Departure date YYYY-MM-DD',
                    'return_date': 'Return date YYYY-MM-DD (optional)',
                    'adults': 'Number of adults (default 1)',
                    'currency': 'Currency code (default USD)',
                },
                returns=('list[FlightOffer] — price_total covers ALL passengers on '
                         'the booking; price_per_passenger is the per-person fare'),
            ),
            ToolCapability(
                name='find_date_deals',
                description=(
                    'Find the cheapest travel window when the traveller gave no fixed '
                    'dates, or wants to know whether shifting helps. Searches several '
                    'departure dates around an anchor and returns the cheapest fare '
                    'for each, so windows can be compared.'
                ),
                parameters={
                    'origin': 'IATA airport code to fly from',
                    'destination': 'IATA airport code to fly to',
                    'around': 'Anchor date YYYY-MM-DD to search around',
                    'trip_nights': 'Nights away; omit for one-way (default 4)',
                    'flex_days': 'How many days either side of the anchor (default 3, max 7)',
                    'adults': 'Number of adults (default 1)',
                    'currency': 'Currency code (default USD)',
                },
                returns='list[DateWindow] sorted cheapest first',
            ),
            ToolCapability(
                name='verify_offer',
                description='Check if an offer is still available and priced',
                parameters={'offer_id': 'The offer ID to verify'},
                returns='OfferDetails',
            ),
            ToolCapability(
                name='confirm_price',
                description='Lock in the price for an offer',
                parameters={'offer_id': 'The offer ID'},
                returns='PriceConfirmation',
            ),
        ]
    
    def execute(self, capability: str, params: Dict[str, Any]) -> ToolResult:
        if capability == 'search_flights':
            return self._search_flights(params)
        elif capability == 'find_date_deals':
            return self._find_date_deals(params)
        elif capability == 'verify_offer':
            return self._verify_offer(params)
        elif capability == 'confirm_price':
            return self._confirm_price(params)
        else:
            raise ToolError(
                f"Unknown capability: {capability}",
                tool_name=self.name,
                capability=capability,
            )
    
    def _search_flights(self, params: Dict[str, Any]) -> ToolResult:
        origin = params.get('origin', '')
        destination = params.get('destination', '')
        depart = params.get('depart', '')
        adults = params.get('adults', 1)
        currency = params.get('currency', 'USD')
        return_date = params.get('return_date')
        
        if not all([origin, destination, depart]):
            return ToolResult(
                status=ToolStatus.ERROR,
                message='origin, destination, and depart are required',
                error='Missing required parameters',
            )
        
        try:
            envelope = self._cli.search(
                origin=origin,
                destination=destination,
                depart=depart,
                return_date=return_date,
                adults=int(adults),
                currency=currency,
            )
            
            if envelope.is_error():
                return ToolResult(
                    status=ToolStatus.ERROR,
                    message=envelope.message,
                    error=envelope.code,
                    raw_response=envelope.raw,
                )
            
            offers = envelope.get_data('offers', [])
            search_id = envelope.get_data('search_id', '')
            
            if not offers:
                return ToolResult(
                    status=ToolStatus.NO_RESULTS,
                    message=f'No flights found {origin}→{destination} on {depart}',
                    data={'search_id': search_id, 'offers': []},
                )
            
            # Normalize offers into a consistent shape
            normalized = [self._normalize_offer(o, int(adults)) for o in offers]
            
            return ToolResult(
                status=ToolStatus.SUCCESS,
                data={
                    'search_id': search_id,
                    'origin': origin,
                    'destination': destination,
                    'depart': depart,
                    'offers': normalized,
                    'count': len(normalized),
                },
                message=f'Found {len(normalized)} flights {origin}→{destination}',
                raw_response=envelope.raw,
            )
            
        except AtlasError as e:
            return ToolResult(
                status=ToolStatus.ERROR,
                message=str(e),
                error=getattr(e, 'code', 'ATLAS_ERROR'),
            )
        except Exception as e:
            return ToolResult(
                status=ToolStatus.ERROR,
                message=f'Flight search failed: {str(e)}',
                error='SEARCH_FAILED',
            )
    
    def _find_date_deals(self, params: Dict[str, Any]) -> ToolResult:
        """Price several departure dates so windows can be compared.

        Exists because travellers routinely say "sometime in October, whenever
        is cheapest" — the plain search needs an exact date and cannot answer
        that. Each window is a real search; nothing here is interpolated.
        """
        import time
        from concurrent.futures import ThreadPoolExecutor
        from datetime import datetime, timedelta

        origin = params.get('origin', '')
        destination = params.get('destination', '')
        around = params.get('around', '')
        if not all([origin, destination, around]):
            return ToolResult(status=ToolStatus.ERROR,
                              message='origin, destination and around are required',
                              error='Missing required parameters')

        try:
            anchor = datetime.strptime(around, '%Y-%m-%d')
        except ValueError:
            return ToolResult(status=ToolStatus.ERROR,
                              message=f'around must be YYYY-MM-DD, got {around!r}',
                              error='Invalid date')

        flex = max(1, min(int(params.get('flex_days', 3) or 3), 7))
        nights = params.get('trip_nights', 4)
        nights = int(nights) if nights not in (None, '', 0) else 0
        adults = int(params.get('adults', 1) or 1)
        currency = params.get('currency', 'USD') or 'USD'

        offsets = list(range(-flex, flex + 1))
        candidates = []
        for delta in offsets:
            depart = anchor + timedelta(days=delta)
            if depart.date() < datetime.utcnow().date():
                continue  # No sense pricing a window that has already gone.
            back = (depart + timedelta(days=nights)).strftime('%Y-%m-%d') if nights else None
            candidates.append((depart.strftime('%Y-%m-%d'), back))

        if not candidates:
            return ToolResult(status=ToolStatus.NO_RESULTS,
                              data={'windows': []},
                              message='Every window in that range is already in the past')

        failures = []

        def price(window):
            depart, back = window
            result = None
            for attempt in range(2):
                try:
                    result = self._search_flights({
                        'origin': origin, 'destination': destination, 'depart': depart,
                        'return_date': back, 'adults': adults, 'currency': currency,
                    })
                    if result.is_success():
                        break
                except Exception as exc:
                    logger.warning('Date deal search failed for %s: %s', depart, exc)
                    result = None
                if attempt == 0:
                    time.sleep(0.4)  # brief backoff before the one retry
            if result is None or not result.is_success():
                failures.append(depart)
                return None
            offers = result.data.get('offers') or []
            if not offers:
                return None
            best = min(offers, key=lambda o: o.get('price_total', 1e9))
            return {
                'offer': best,
                'depart': depart,
                'return_date': back,
                'nights': nights or None,
                'price_total': best['price_total'],
                'price_per_passenger': best.get('price_per_passenger'),
                'currency': best.get('currency', currency),
                'airline': best.get('airline', ''),
                'flight_code': best.get('flight_code', ''),
                'offer_id': best.get('offer_id', ''),
                'options_found': len(offers),
            }

        # Each window is an independent CLI call; run them together or a
        # seven-day sweep takes the better part of a minute. Three at a time is
        # as much as the CLI reliably tolerates.
        with ThreadPoolExecutor(max_workers=3) as pool:
            windows = [w for w in pool.map(price, candidates) if w]

        if not windows:
            return ToolResult(
                status=ToolStatus.NO_RESULTS,
                data={'origin': origin, 'destination': destination, 'windows': []},
                message=(f'No fares found {origin}→{destination} in the '
                         f'{len(candidates)} windows around {around}'),
            )

        windows.sort(key=lambda w: w['price_total'])
        cheapest, anchor_window = windows[0], next(
            (w for w in windows if w['depart'] == around), None)
        saving = (round(anchor_window['price_total'] - cheapest['price_total'], 2)
                  if anchor_window else None)

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                'origin': origin, 'destination': destination,
                'anchor': around, 'windows_checked': len(candidates),
                'windows': windows, 'count': len(windows),
                'cheapest': cheapest,
                'saving_vs_anchor': saving,
                'currency': cheapest['currency'],
                'unpriced_dates': sorted(failures),
            },
            message=(
                f"Cheapest is {cheapest['depart']} at {cheapest['currency']} "
                f"{cheapest['price_total']:.2f}"
                + (f", {saving:.2f} less than {around}" if saving and saving > 0 else '')
                + f" ({len(windows)} of {len(candidates)} windows priced"
                + (f"; no fare returned for {', '.join(sorted(failures))}" if failures else '')
                + ")"
            ),
        )

    def _verify_offer(self, params: Dict[str, Any]) -> ToolResult:
        offer_id = params.get('offer_id', '')
        if not offer_id:
            return ToolResult(
                status=ToolStatus.ERROR,
                message='offer_id is required',
                error='Missing parameter',
            )
        
        try:
            envelope = self._cli.offer_verify(offer_id)
            if envelope.is_error():
                return ToolResult(
                    status=ToolStatus.ERROR,
                    message=envelope.message,
                    error=envelope.code,
                )
            return ToolResult(
                status=ToolStatus.SUCCESS,
                data=envelope.data,
                message='Offer verified',
                raw_response=envelope.raw,
            )
        except AtlasError as e:
            return ToolResult(
                status=ToolStatus.ERROR,
                message=str(e),
                error=getattr(e, 'code', 'VERIFY_FAILED'),
            )
    
    def _confirm_price(self, params: Dict[str, Any]) -> ToolResult:
        offer_id = params.get('offer_id', '')
        if not offer_id:
            return ToolResult(
                status=ToolStatus.ERROR,
                message='offer_id is required',
                error='Missing parameter',
            )
        
        try:
            envelope = self._cli.booking_confirm_price(offer_id)
            if envelope.is_error():
                return ToolResult(
                    status=ToolStatus.ERROR,
                    message=envelope.message,
                    error=envelope.code,
                )
            return ToolResult(
                status=ToolStatus.SUCCESS,
                data=envelope.data,
                message='Price confirmed',
                raw_response=envelope.raw,
            )
        except AtlasError as e:
            return ToolResult(
                status=ToolStatus.ERROR,
                message=str(e),
                error=getattr(e, 'code', 'PRICE_CONFIRM_FAILED'),
            )
    
    @staticmethod
    def _leg(segments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Collapse consecutive segments into one described leg."""
        if not segments:
            return {}
        first, last = segments[0], segments[-1]
        carrier = first.get('carrier', '')
        number = first.get('flight_number', '')
        # Atlas already prefixes the carrier onto the flight number, so joining
        # the two fields renders "AKAK374".
        code = number if number.upper().startswith(carrier.upper()) and carrier else f'{carrier}{number}'
        return {
            'flight_code': code,
            'origin': first.get('departure_airport', ''),
            'destination': last.get('arrival_airport', ''),
            'depart': AtlasTool._fmt_time(first.get('departure_time', '')),
            'arrive': AtlasTool._fmt_time(last.get('arrival_time', '')),
            'airline': first.get('carrier', ''),
            'flight_number': first.get('flight_number', ''),
            'duration_minutes': sum(s.get('duration_minutes', 0) or 0 for s in segments),
            'stops': max(0, len(segments) - 1),
        }

    @staticmethod
    def _fmt_time(raw: str) -> str:
        """Atlas returns YYYYMMDDHHMM; give back an ISO-ish string."""
        digits = str(raw or '')
        if len(digits) != 12 or not digits.isdigit():
            return digits
        return (f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"
                f"T{digits[8:10]}:{digits[10:12]}")

    @staticmethod
    def _split_legs(segments: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """Split a round trip into outbound and return.

        Atlas returns every segment in one flat list. The return leg is the
        first segment that heads back toward the original departure airport.
        """
        if len(segments) < 2:
            return [segments] if segments else []
        origin = segments[0].get('departure_airport')
        for i in range(1, len(segments)):
            if segments[i].get('arrival_airport') == origin:
                return [segments[:i], segments[i:]]
        return [segments]

    @staticmethod
    def _normalize_offer(raw: Dict[str, Any], passengers: int = 1) -> Dict[str, Any]:
        """Normalize a raw Atlas offer.

        Atlas quotes `total_price` for the WHOLE party, not per traveller. The
        old shape exposed that as a bare `price`, and the agent duly reported
        it as the per-person fare, doubling a two-adult trip. The price fields
        are now named for exactly what they hold.
        """
        segments = raw.get('segments', []) or []
        legs = AtlasTool._split_legs(segments)

        total = raw.get('total_price', raw.get('price', 0)) or 0
        pax_prices = raw.get('passenger_prices') or []
        pax_count = passengers
        per_person = None
        if pax_prices:
            entry = pax_prices[0]
            pax_count = entry.get('count', passengers) or passengers
            base = entry.get('base_fare_per_passenger')
            tax = entry.get('tax_per_passenger')
            if base is not None and tax is not None:
                per_person = round(base + tax, 2)
        if per_person is None and pax_count:
            per_person = round(total / pax_count, 2)

        outbound = AtlasTool._leg(legs[0]) if legs else {}
        inbound = AtlasTool._leg(legs[1]) if len(legs) > 1 else None

        return {
            'offer_id': raw.get('offer_id', raw.get('id', '')),
            'airline': outbound.get('airline', ''),
            'flight_number': outbound.get('flight_number', ''),
            'flight_code': outbound.get('flight_code', ''),
            'origin': outbound.get('origin', ''),
            'destination': outbound.get('destination', ''),
            'departure_time': outbound.get('depart', ''),
            'arrival_time': outbound.get('arrive', ''),
            'duration_minutes': outbound.get('duration_minutes', 0),
            'stops': outbound.get('stops', 0),
            'outbound': outbound,
            'return_leg': inbound,
            'round_trip': inbound is not None,
            # Explicit money. `price_total` covers everyone on the booking.
            'price_total': round(float(total), 2),
            'price_per_passenger': per_person,
            'passengers': pax_count,
            'price': round(float(total), 2),  # legacy alias, same total
            'currency': raw.get('currency', 'USD'),
            'fare_family': raw.get('fare_family', ''),
            'seats_available': raw.get('seats_available', 9),
            'baggage_included': raw.get('baggage_included', False),
            'segments': segments,
        }


# Auto-register on import
from .registry import tool_registry
tool_registry.register(AtlasTool())
