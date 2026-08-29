"""
Search and Ranking Engine
Finds and ranks replacement flight options for disrupted itineraries
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import json

from ..cli import AtlasCLI, AtlasEnvelope, SearchError, OfferError


@dataclass
class DisruptedItinerary:
    """Represents a disrupted flight itinerary"""
    origin: str
    destination: str
    original_departure: datetime
    passengers: int
    hard_deadline: Optional[datetime] = None  # Must arrive before this time
    notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'origin': self.origin,
            'destination': self.destination,
            'original_departure': self.original_departure.isoformat(),
            'passengers': self.passengers,
            'hard_deadline': self.hard_deadline.isoformat() if self.hard_deadline else None,
            'notes': self.notes
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DisruptedItinerary':
        return cls(
            origin=data['origin'],
            destination=data['destination'],
            original_departure=datetime.fromisoformat(data['original_departure'].replace('Z', '+00:00')),
            passengers=data.get('passengers', 1),
            hard_deadline=datetime.fromisoformat(data['hard_deadline'].replace('Z', '+00:00')) if data.get('hard_deadline') else None,
            notes=data.get('notes', '')
        )


@dataclass
class RankedOption:
    """A flight option with ranking metadata"""
    offer_id: str
    airline: str
    flight_number: str
    departure: datetime
    arrival: datetime
    duration_minutes: int
    price: float
    currency: str
    fare_family: str
    seats_available: int
    baggage_included: bool
    rank: int
    meets_deadline: bool
    tradeoff: str
    score: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'offer_id': self.offer_id,
            'airline': self.airline,
            'flight_number': self.flight_number,
            'departure': self.departure.isoformat(),
            'arrival': self.arrival.isoformat(),
            'duration_minutes': self.duration_minutes,
            'price': self.price,
            'currency': self.currency,
            'fare_family': self.fare_family,
            'seats_available': self.seats_available,
            'baggage_included': self.baggage_included,
            'rank': self.rank,
            'meets_deadline': self.meets_deadline,
            'tradeoff': self.tradeoff,
            'score': self.score
        }


class SearchEngine:
    """Searches for and ranks replacement flight options"""
    
    def __init__(self, cli: AtlasCLI):
        self.cli = cli
        self.search_id: Optional[str] = None
        self.itinerary: Optional[DisruptedItinerary] = None
    
    def search(self, itinerary: DisruptedItinerary) -> List[RankedOption]:
        """Search for replacement flights and rank them"""
        self.itinerary = itinerary
        
        # Step 1: Execute search — offers come directly in the response
        search_result = self.cli.search(
            origin=itinerary.origin,
            destination=itinerary.destination,
            depart=itinerary.original_departure.strftime('%Y-%m-%d'),
            adults=itinerary.passengers
        )
        
        if search_result.is_error():
            raise SearchError(
                f"Search failed: {search_result.message}",
                code=search_result.code,
                retryable=search_result.retryable
            )
        
        self.search_id = search_result.get_data('search_id')
        
        # Offers are returned directly in the search response
        offers = search_result.get_data('offers', [])
        
        if not offers:
            raise SearchError(
                "No flights found for this route and date",
                code='NO_RESULTS',
                retryable=False
            )
        
        # Step 2: Rank offers
        ranked = self._rank_offers(offers, itinerary)
        
        return ranked
    
    def _rank_offers(
        self,
        offers: List[Dict[str, Any]],
        itinerary: DisruptedItinerary
    ) -> List[RankedOption]:
        """Rank offers based on traveler constraints"""
        ranked_options = []
        
        for offer in offers:
            # Parse segments — real Atlas data nests flight details in segments
            segments = offer.get('segments', [])
            if not segments:
                continue
            
            segment = segments[0]  # Primary segment
            
            # Parse departure/arrival times from Atlas format (YYYYMMDDHHMM)
            dep_str = segment.get('departure_time', '')
            arr_str = segment.get('arrival_time', '')
            
            try:
                departure = datetime.strptime(dep_str, '%Y%m%d%H%M')
                arrival = datetime.strptime(arr_str, '%Y%m%d%H%M')
            except ValueError:
                # Fallback: try ISO format
                try:
                    departure = datetime.fromisoformat(dep_str.replace('Z', '+00:00'))
                    arrival = datetime.fromisoformat(arr_str.replace('Z', '+00:00'))
                except ValueError:
                    continue
            
            # Extract real data from Atlas response
            offer_id = offer.get('offer_id', '')
            airline = segment.get('carrier', '')
            flight_number = segment.get('flight_number', '')
            duration_minutes = segment.get('duration_minutes', 0)
            price = offer.get('total_price', 0)
            currency = offer.get('currency', 'USD')
            
            # Check if meets deadline
            meets_deadline = True
            deadline_penalty = 0
            if itinerary.hard_deadline:
                # Compare arrival with deadline (handle timezone-naive comparison)
                deadline = itinerary.hard_deadline.replace(tzinfo=None)
                if arrival > deadline:
                    meets_deadline = False
                    deadline_penalty = (arrival - deadline).total_seconds() / 60
            
            # Calculate time proximity score (closer to original departure = better)
            orig_dep = itinerary.original_departure.replace(tzinfo=None)
            time_diff = abs((departure - orig_dep).total_seconds()) / 3600  # hours
            time_score = max(0, 100 - (time_diff * 5))  # Lose 5 points per hour difference
            
            # Price score (lower = better, normalize to 0-100)
            max_price = max(o.get('total_price', 100) for o in offers)
            price_score = max(0, 100 - (price / max_price * 100))
            
            # Duration score (shorter = better)
            max_duration = max(s.get('duration_minutes', 60) for o in offers for s in o.get('segments', [{}]))
            duration_score = max(0, 100 - (duration_minutes / max_duration * 100))
            
            # Composite score
            if meets_deadline:
                score = (
                    time_score * 0.3 +
                    price_score * 0.4 +
                    duration_score * 0.3
                )
            else:
                score = (
                    deadline_penalty * -10 +
                    time_score * 0.15 +
                    price_score * 0.2 +
                    duration_score * 0.15
                )
            
            # Determine fare family from ancillary support
            ancillary = offer.get('ancillary_supported', [])
            fare_family = 'Basic'
            if 'baggage' in ancillary and 'seat' in ancillary:
                fare_family = 'Flex'
            
            ranked_options.append(RankedOption(
                offer_id=offer_id,
                airline=airline,
                flight_number=flight_number,
                departure=departure,
                arrival=arrival,
                duration_minutes=duration_minutes,
                price=price,
                currency=currency,
                fare_family=fare_family,
                seats_available=5,  # Atlas sandbox doesn't return seat count
                baggage_included='baggage' in ancillary,
                rank=0,
                meets_deadline=meets_deadline,
                tradeoff="",
                score=score
            ))
        
        # Sort by score (descending)
        ranked_options.sort(key=lambda x: x.score, reverse=True)
        
        # Assign ranks
        for i, option in enumerate(ranked_options, 1):
            option.rank = i
        
        return ranked_options
    
    def get_top_options(self, count: int = 3) -> List[RankedOption]:
        """Get top N ranked options"""
        if not self.itinerary:
            raise ValueError("Must call search() before get_top_options()")
        
        # Re-search to get options
        options = self.search(self.itinerary)
        return options[:count]
