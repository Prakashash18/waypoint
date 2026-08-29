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
                returns='list[FlightOffer]',
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
            normalized = [self._normalize_offer(o) for o in offers]
            
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
    def _normalize_offer(raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a raw Atlas offer into a consistent shape."""
        segments = raw.get('segments', [{}])
        seg = segments[0] if segments else {}
        
        return {
            'offer_id': raw.get('offer_id', raw.get('id', '')),
            'airline': seg.get('carrier', raw.get('carrier', '')),
            'flight_number': seg.get('flight_number', ''),
            'departure_time': seg.get('departure_time', ''),
            'arrival_time': seg.get('arrival_time', ''),
            'origin': seg.get('origin', ''),
            'destination': seg.get('destination', ''),
            'duration_minutes': seg.get('duration_minutes', 0),
            'price': raw.get('total_price', raw.get('price', 0)),
            'currency': raw.get('currency', 'USD'),
            'fare_family': raw.get('fare_family', ''),
            'seats_available': raw.get('seats_available', 9),
            'baggage_included': raw.get('baggage_included', False),
            'segments': segments,
        }


# Auto-register on import
from .registry import tool_registry
tool_registry.register(AtlasTool())
