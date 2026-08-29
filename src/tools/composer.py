"""TripComposer — the agent brain that plans trips across multiple tools.

Takes a TripRequest, dispatches parallel searches to the tool registry,
composes packages (flight + hotel), ranks them, and returns results.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base import ToolResult, ToolStatus
from .registry import ToolRegistry, tool_registry

logger = logging.getLogger(__name__)


@dataclass
class TripRequest:
    """What the user wants — extracted from conversation."""
    origin: str = ''                        # IATA code or city name
    destination: str = ''                   # IATA code or city name
    depart_date: str = ''                   # YYYY-MM-DD
    return_date: str = ''                   # YYYY-MM-DD (optional)
    adults: int = 2
    children: int = 0
    budget: float = 0                       # Total budget in USD (0 = no limit)
    currency: str = 'USD'
    preferences: Dict[str, Any] = field(default_factory=dict)
    # Preference keys: pool (bool), stars_min (int), flexible_dates (bool),
    #                  cabin_class (str), hotel_area (str), etc.
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'origin': self.origin,
            'destination': self.destination,
            'depart_date': self.depart_date,
            'return_date': self.return_date,
            'adults': self.adults,
            'children': self.children,
            'budget': self.budget,
            'currency': self.currency,
            'preferences': self.preferences,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TripRequest':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
    
    @property
    def nights(self) -> int:
        if not self.depart_date or not self.return_date:
            return 0
        try:
            ci = datetime.strptime(self.depart_date, '%Y-%m-%d')
            co = datetime.strptime(self.return_date, '%Y-%m-%d')
            return max(1, (co - ci).days)
        except ValueError:
            return 0


@dataclass
class TripPackage:
    """A composed travel package — flights + hotel bundled together."""
    label: str = ''                         # "Smart Pick", "Budget", "Comfort"
    flights: List[Dict[str, Any]] = field(default_factory=list)
    hotels: List[Dict[str, Any]] = field(default_factory=list)
    total_price: float = 0
    flight_price: float = 0
    hotel_price: float = 0
    currency: str = 'USD'
    score: float = 0                        # Ranking score
    reasoning: str = ''                     # Why this package is good
    over_budget: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'label': self.label,
            'flights': self.flights,
            'hotel': self.hotels[0] if self.hotels else None,
            'total_price': self.total_price,
            'flight_price': self.flight_price,
            'hotel_price': self.hotel_price,
            'currency': self.currency,
            'score': self.score,
            'reasoning': self.reasoning,
            'over_budget': self.over_budget,
        }


class TripComposer:
    """Plans trips by orchestrating multiple tools.
    
    Flow:
    1. Dispatch parallel searches (flights + hotels)
    2. Collect results
    3. Compose packages (match flights with hotels)
    4. Rank and label packages
    5. Return top N with reasoning
    """
    
    # City name → IATA airport code mapping
    CITY_TO_IATA = {
        # ── Southeast Asia (original) ────────────────────────────
        'bali': 'DPS',
        'singapore': 'SIN',
        'bangkok': 'BKK',
        'kuala lumpur': 'KUL',
        'tokyo': 'NRT',
        'seoul': 'ICN',
        'hong kong': 'HKG',
        'penang': 'PEN',
        'phuket': 'HKT',
        'chiang mai': 'CNX',
        'jakarta': 'CGK',
        'ho chi minh': 'SGN',
        'hanoi': 'HAN',
        'manila': 'MNL',
        'colombo': 'CMB',
        'phnom penh': 'PNH',
        'siem reap': 'REP',
        'yangon': 'RGN',
        # ── Aliases ───────────────────────────────────────────────
        'kl': 'KUL',
        'hcmc': 'SGN',
        'ho chi minh city': 'SGN',
        'chiangmai': 'CNX',
        # ── Americas ──────────────────────────────────────────────
        'new york': 'JFK',
        'los angeles': 'LAX',
        'san francisco': 'SFO',
        'chicago': 'ORD',
        'miami': 'MIA',
        'atlanta': 'ATL',
        'dallas': 'DFW',
        'seattle': 'SEA',
        'boston': 'BOS',
        'denver': 'DEN',
        'houston': 'IAH',
        'phoenix': 'PHX',
        'honolulu': 'HNL',
        'toronto': 'YYZ',
        'vancouver': 'YVR',
        'montreal': 'YUL',
        'mexico city': 'MEX',
        'cancun': 'CUN',
        'sao paulo': 'GRU',
        'rio de janeiro': 'GIG',
        'buenos aires': 'EZE',
        'santiago': 'SCL',
        'lima': 'LIM',
        'bogota': 'BOG',
        # ── Americas aliases ──────────────────────────────────────
        'new york city': 'JFK',
        'nyc': 'JFK',
        'la': 'LAX',
        'sf': 'SFO',
        'dc': 'IAD',
        'washington': 'IAD',
        'mexico': 'MEX',
        # ── Europe ────────────────────────────────────────────────
        'london': 'LHR',
        'paris': 'CDG',
        'amsterdam': 'AMS',
        'frankfurt': 'FRA',
        'munich': 'MUC',
        'berlin': 'BER',
        'madrid': 'MAD',
        'barcelona': 'BCN',
        'rome': 'FCO',
        'milan': 'MXP',
        'zurich': 'ZRH',
        'vienna': 'VIE',
        'brussels': 'BRU',
        'lisbon': 'LIS',
        'athens': 'ATH',
        'istanbul': 'IST',
        'copenhagen': 'CPH',
        'oslo': 'OSL',
        'stockholm': 'ARN',
        'helsinki': 'HEL',
        'dublin': 'DUB',
        'edinburgh': 'EDI',
        'manchester': 'MAN',
        'warsaw': 'WAW',
        'prague': 'PRG',
        'budapest': 'BUD',
        'reykjavik': 'KEF',
        # ── Middle East ───────────────────────────────────────────
        'dubai': 'DXB',
        'abu dhabi': 'AUH',
        'doha': 'DOH',
        'riyadh': 'RUH',
        'jeddah': 'JED',
        'muscat': 'MCT',
        'bahrain': 'BAH',
        'tel aviv': 'TLV',
        'amman': 'AMM',
        # ── Africa ────────────────────────────────────────────────
        'cairo': 'CAI',
        'casablanca': 'CMN',
        'nairobi': 'NBO',
        'johannesburg': 'JNB',
        'cape town': 'CPT',
        'lagos': 'LOS',
        'addis ababa': 'ADD',
        'dar es salaam': 'DAR',
        'mauritius': 'MRU',
        # ── South Asia ────────────────────────────────────────────
        'delhi': 'DEL',
        'mumbai': 'BOM',
        'bangalore': 'BLR',
        'chennai': 'MAA',
        'kathmandu': 'KTM',
        'dhaka': 'DAC',
        'islamabad': 'ISB',
        # ── East Asia ─────────────────────────────────────────────
        'taipei': 'TPE',
        'shanghai': 'PVG',
        'beijing': 'PEK',
        'osaka': 'KIX',
        # ── Oceania ───────────────────────────────────────────────
        'sydney': 'SYD',
        'melbourne': 'MEL',
        'brisbane': 'BNE',
        'perth': 'PER',
        'auckland': 'AKL',
        'wellington': 'WLG',
        'fiji': 'NAN',
        'male': 'MLE',  # Maldives
    }
    
    def __init__(self, registry: Optional[ToolRegistry] = None):
        self.registry = registry or tool_registry
    
    def _resolve_iata(self, name: str) -> str:
        """Resolve a city name or IATA code to an IATA code."""
        if not name:
            return ''
        # Strip parenthetical IATA code suffix e.g. "Bangkok (BKK)" -> "Bangkok"
        clean = re.sub(r'\s*\([A-Z]{3}\)\s*$', '', name.strip())
        # Already an IATA code (3 uppercase letters)
        if len(clean) == 3 and clean.isalpha() and clean.isupper():
            return clean
        # Look up in mapping
        return self.CITY_TO_IATA.get(clean.lower().strip(), clean.upper().strip())
    
    def plan(self, request: TripRequest) -> Dict[str, Any]:
        """Plan a trip — main entry point.
        
        Returns dict with:
            packages: list[TripPackage]
            flight_results: raw flight search result
            hotel_results: raw hotel search result
            summary: text summary
        """
        logger.info(f"Planning trip: {request.origin}→{request.destination}, "
                     f"{request.depart_date}–{request.return_date}, "
                     f"{request.adults} adults, budget ${request.budget}")
        
        # Step 1: Dispatch parallel searches
        flight_result, hotel_result = self._dispatch_search(request)
        
        # Step 2: Extract data
        flights = self._extract_flights(flight_result)
        hotels = self._extract_hotels(hotel_result)
        
        if not flights:
            return {
                'packages': [],
                'summary': f"Sorry, I couldn't find any flights from {request.origin} to {request.destination} on {request.depart_date}. Try a different date or route.",
                'flight_results': flight_result.to_dict() if flight_result else None,
                'hotel_results': hotel_result.to_dict() if hotel_result else None,
            }
        
        if not hotels:
            return {
                'packages': [],
                'summary': f"I found flights but no hotels in {request.destination}. Want me to search again with different criteria?",
                'flight_results': flight_result.to_dict() if flight_result else None,
                'hotel_results': hotel_result.to_dict() if hotel_result else None,
            }
        
        # Step 3: Compose packages
        packages = self._compose_packages(flights, hotels, request)
        
        # Step 4: Rank and label
        packages = self._rank_packages(packages, request)
        
        # Step 5: Generate summary
        summary = self._generate_summary(packages, request)
        
        return {
            'packages': [p.to_dict() for p in packages],
            'summary': summary,
            'flight_count': len(flights),
            'hotel_count': len(hotels),
        }
    
    def _dispatch_search(self, request: TripRequest):
        """Run flight + hotel searches in parallel."""
        flight_result = None
        hotel_result = None
        
        # Resolve IATA codes for flights (keep city names for hotels)
        origin_iata = self._resolve_iata(request.origin)
        dest_iata = self._resolve_iata(request.destination)
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {}
            
            # Flight search (uses IATA codes)
            if origin_iata and dest_iata and request.depart_date:
                futures[executor.submit(
                    self.registry.execute,
                    'atlas_flights',
                    'search_flights',
                    {
                        'origin': origin_iata,
                        'destination': dest_iata,
                        'depart': request.depart_date,
                        'adults': request.adults,
                        'currency': request.currency,
                        'return_date': request.return_date or None,
                    }
                )] = 'flights'
            
            # Hotel search
            if request.destination and request.depart_date and request.return_date:
                futures[executor.submit(
                    self.registry.execute,
                    'hotels',
                    'search_hotels',
                    {
                        'destination': request.destination,
                        'check_in': request.depart_date,
                        'check_out': request.return_date,
                        'adults': request.adults,
                        'children': request.children,
                        'currency': request.currency,
                    }
                )] = 'hotels'
            
            for future in as_completed(futures):
                search_type = futures[future]
                try:
                    result = future.result()
                    if search_type == 'flights':
                        flight_result = result
                    elif search_type == 'hotels':
                        hotel_result = result
                except Exception as e:
                    logger.error(f"Search {search_type} failed: {e}")
        
        return flight_result, hotel_result
    
    def _extract_flights(self, result: Optional[ToolResult]) -> List[Dict[str, Any]]:
        """Extract normalized flight offers from a ToolResult."""
        if not result or not result.has_data():
            return []
        offers = result.data.get('offers', [])
        # Sort by price (cheapest first)
        offers.sort(key=lambda o: o.get('price', 999999))
        return offers
    
    def _extract_hotels(self, result: Optional[ToolResult]) -> List[Dict[str, Any]]:
        """Extract normalized hotel offers from a ToolResult."""
        if not result or not result.has_data():
            return []
        hotels = result.data.get('hotels', [])
        # Sort by total_price (cheapest first)
        hotels.sort(key=lambda h: h.get('total_price', 999999))
        return hotels
    
    def _compose_packages(
        self,
        flights: List[Dict[str, Any]],
        hotels: List[Dict[str, Any]],
        request: TripRequest,
    ) -> List[TripPackage]:
        """Compose flight + hotel combinations.
        
        Strategy:
        - Budget package: cheapest flight + cheapest hotel
        - Smart pick: mid-range flight + best-rated hotel under budget
        - Comfort: best flight + best hotel (may exceed budget)
        """
        packages = []
        
        # --- Budget Package ---
        cheapest_flight = flights[0] if flights else None
        cheapest_hotel = min(hotels, key=lambda h: h.get('total_price', 999999)) if hotels else None
        
        if cheapest_flight and cheapest_hotel:
            f_price = cheapest_flight.get('price', 0) * request.adults
            h_price = cheapest_hotel.get('total_price', 0)
            packages.append(TripPackage(
                flights=[cheapest_flight],
                hotels=[cheapest_hotel],
                flight_price=f_price,
                hotel_price=h_price,
                total_price=f_price + h_price,
                currency=request.currency,
            ))
        
        # --- Smart Pick: best value ---
        # Pick flight closest to morning departure + mid-range price
        mid_flight = self._pick_mid_flight(flights)
        # Pick hotel with best rating that has a pool (if preferred)
        smart_hotel = self._pick_smart_hotel(hotels, request)
        
        if mid_flight and smart_hotel:
            f_price = mid_flight.get('price', 0) * request.adults
            h_price = smart_hotel.get('total_price', 0)
            packages.append(TripPackage(
                flights=[mid_flight],
                hotels=[smart_hotel],
                flight_price=f_price,
                hotel_price=h_price,
                total_price=f_price + h_price,
                currency=request.currency,
            ))
        
        # --- Comfort: best experience ---
        best_flight = self._pick_best_flight(flights)
        best_hotel = self._pick_best_hotel(hotels)
        
        if best_flight and best_hotel:
            f_price = best_flight.get('price', 0) * request.adults
            h_price = best_hotel.get('total_price', 0)
            packages.append(TripPackage(
                flights=[best_flight],
                hotels=[best_hotel],
                flight_price=f_price,
                hotel_price=h_price,
                total_price=f_price + h_price,
                currency=request.currency,
            ))
        
        # Deduplicate (in case strategies picked the same items)
        seen = set()
        unique = []
        for pkg in packages:
            key = (
                pkg.flights[0].get('offer_id', '') if pkg.flights else '',
                pkg.hotels[0].get('hotel_id', '') if pkg.hotels else '',
            )
            if key not in seen:
                seen.add(key)
                unique.append(pkg)
        
        return unique
    
    def _pick_mid_flight(self, flights: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Pick a mid-range flight (not cheapest, not most expensive)."""
        if len(flights) < 3:
            return flights[0] if flights else None
        return flights[len(flights) // 3]
    
    def _pick_best_flight(self, flights: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Pick the best flight (most seats, shortest duration)."""
        if not flights:
            return None
        return min(flights, key=lambda f: (
            f.get('duration_minutes', 9999),
            -f.get('seats_available', 0),
        ))
    
    def _pick_smart_hotel(self, hotels: List[Dict[str, Any]], request: TripRequest) -> Optional[Dict[str, Any]]:
        """Pick the best-value hotel matching preferences."""
        want_pool = request.preferences.get('pool', True)
        min_stars = request.preferences.get('stars_min', 0)
        
        candidates = hotels
        if want_pool:
            candidates = [h for h in hotels if h.get('has_pool')]
        if min_stars:
            candidates = [h for h in candidates if h.get('stars', 0) >= min_stars]
        
        if not candidates:
            candidates = hotels
        
        # Best rating among candidates
        return max(candidates, key=lambda h: h.get('rating', 0)) if candidates else None
    
    def _pick_best_hotel(self, hotels: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Pick the best hotel regardless of price."""
        if not hotels:
            return None
        return max(hotels, key=lambda h: (h.get('stars', 0), h.get('rating', 0)))
    
    def _rank_packages(self, packages: List[TripPackage], request: TripRequest) -> List[TripPackage]:
        """Rank packages and assign labels."""
        budget = request.budget
        
        # Score each package
        for pkg in packages:
            score = 0
            pkg.over_budget = budget > 0 and pkg.total_price > budget
            
            # Budget compliance (biggest factor)
            if budget > 0:
                if pkg.total_price <= budget:
                    under_pct = (budget - pkg.total_price) / budget
                    score += 40 * min(under_pct * 3, 1)  # Up to 40 points
                else:
                    over_pct = (pkg.total_price - budget) / budget
                    score -= 30 * min(over_pct * 2, 1)   # Penalty
            
            # Hotel quality
            if pkg.hotels:
                h = pkg.hotels[0]
                score += h.get('rating', 3) * 5          # Up to 25 points
                score += h.get('stars', 0) * 2           # Up to 10 points
                if h.get('has_pool'):
                    score += 5
                if h.get('free_cancellation'):
                    score += 3
            
            # Flight quality
            if pkg.flights:
                f = pkg.flights[0]
                score += f.get('seats_available', 0) * 0.5
            
            pkg.score = round(score, 1)
        
        # Sort by score (highest first)
        packages.sort(key=lambda p: p.score, reverse=True)
        
        # Assign labels
        labels = ['Smart Pick', 'Budget', 'Comfort', 'Alternative']
        for i, pkg in enumerate(packages):
            if i < len(labels):
                pkg.label = labels[i]
        
        # Override labels based on characteristics
        for pkg in packages:
            if budget > 0 and pkg.total_price <= budget * 0.7:
                pkg.label = 'Budget'
            elif budget > 0 and pkg.total_price > budget:
                pkg.label = 'Comfort'
        
        # Generate reasoning for each
        for pkg in packages:
            pkg.reasoning = self._generate_reasoning(pkg, request)
        
        return packages
    
    def _generate_reasoning(self, pkg: TripPackage, request: TripRequest) -> str:
        """Generate human-readable explanation for why this package is good."""
        parts = []
        
        if pkg.hotels:
            h = pkg.hotels[0]
            parts.append(f"{h.get('name', 'Hotel')} ({h.get('stars', 0)}★, {h.get('rating', 0)} rating) in {h.get('area', 'the area')}")
            if h.get('has_pool'):
                parts.append("has a pool")
            if h.get('free_cancellation'):
                parts.append("free cancellation")
            if h.get('breakfast_included'):
                parts.append("breakfast included")
        
        if pkg.flights:
            f = pkg.flights[0]
            dep = f.get('departure_time', '')
            arr = f.get('arrival_time', '')
            parts.append(f"Flight {f.get('airline', '')} {f.get('flight_number', '')} departs {dep}, arrives {arr}")
        
        if request.budget > 0:
            remaining = request.budget - pkg.total_price
            if remaining > 0:
                parts.append(f"${remaining:.0f} under budget — leaves room for food and activities")
            elif remaining < 0:
                parts.append(f"${abs(remaining):.0f} over budget, but premium experience")
        
        return '. '.join(parts) + '.'
    
    def _generate_summary(self, packages: List[TripPackage], request: TripRequest) -> str:
        """Generate a text summary of the results."""
        if not packages:
            return "I couldn't put together any packages. Try adjusting your dates or destination."
        
        lines = [f"I found {len(packages)} trip packages for {request.destination}:"]
        
        for pkg in packages:
            price_str = f"${pkg.total_price:.0f}"
            budget_note = ''
            if request.budget > 0:
                if pkg.total_price <= request.budget:
                    budget_note = f" (under budget by ${request.budget - pkg.total_price:.0f})"
                else:
                    budget_note = f" (${pkg.total_price - request.budget:.0f} over budget)"
            
            hotel_name = pkg.hotels[0].get('name', 'Hotel') if pkg.hotels else 'No hotel'
            flight_info = ''
            if pkg.flights:
                f = pkg.flights[0]
                flight_info = f"Flight {f.get('airline', '')} {f.get('flight_number', '')}"
            
            lines.append(f"\n**{pkg.label}** — {price_str}{budget_note}")
            lines.append(f"🛫 {flight_info}")
            lines.append(f"🏨 {hotel_name}")
            lines.append(f"💡 {pkg.reasoning}")
        
        return '\n'.join(lines)
