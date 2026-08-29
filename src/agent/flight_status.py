"""
Flight Status and Location Services
Provides real-time flight delay information and location-based airport detection
"""

import requests
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging
import os
from .api_tracker import tracker


logger = logging.getLogger(__name__)


class LocationService:
    """Nearest airports for a set of coordinates.

    This used to carry a ten-airport table, which returned nothing for most of
    the world — Lisbon and Denver both came back empty. It now delegates to
    PlacesTool, which queries OpenStreetMap and falls back to a bundled
    reference of major airports. Kept as a thin shim because the UI and the
    older tool both import it.
    """

    @classmethod
    def find_nearby_airports(cls, lat: float, lon: float,
                             radius_km: int = 250) -> List[Dict[str, Any]]:
        """Airports near a point, nearest first.

        Returns the historical shape (`code`, `name`, `city`, `distance_km`) so
        existing callers keep working, with `iata` alongside for new ones.
        """
        from ..tools.places_tool import PlacesTool

        result = PlacesTool().nearest_airports(
            {'lat': lat, 'lon': lon, 'radius_km': radius_km, 'limit': 6})
        if not result.is_success():
            return []

        return [
            {
                'code': airport['iata'],
                'iata': airport['iata'],
                'name': airport['name'],
                'city': airport.get('city', ''),
                'distance_km': airport['distance_km'],
            }
            for airport in result.data.get('airports', [])
        ]

    @classmethod
    def get_airport_by_ip(cls, ip: str = None) -> Optional[Dict[str, Any]]:
        """Nearest airport from an IP address."""
        from ..tools.locale_tool import LocaleTool

        locale = LocaleTool().detect_locale({})
        if not locale.is_success():
            return None
        data = locale.data or {}
        if data.get('lat') is None:
            return None

        nearby = cls.find_nearby_airports(data['lat'], data['lon'], radius_km=250)
        if not nearby:
            return None
        return {**nearby[0], 'location': {'lat': data['lat'], 'lon': data['lon'],
                                          'city': data.get('city', ''),
                                          'country': data.get('country', '')}}

    @staticmethod
    def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points in km"""
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371  # Earth radius in km
        
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
        return R * c


class FlightStatusService:
    """Get real-time flight status and delays"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('AVIATIONSTACK_API_KEY')
        # Why the last call returned nothing, so callers can say so out loud.
        self.last_error: str = ''
    
    def get_delays_from_airport(
        self,
        airport_code: str,
        days: int = 3
    ) -> List[Dict[str, Any]]:
        """Get delayed flights departing an airport.

        Returns real AviationStack data or an empty list. It never returns
        invented flights: a made-up delay would send a traveller rebooking
        around a disruption that is not happening.
        """
        if not self.api_key:
            self.last_error = (
                'AVIATIONSTACK_API_KEY is not set, so live delay data is '
                'unavailable. Sign up free at https://aviationstack.com'
            )
            return []

        return self._get_delays_from_api(airport_code, days)

    def _get_delays_from_api(
        self,
        airport_code: str,
        days: int
    ) -> List[Dict[str, Any]]:
        """Get delays from AviationStack API (free tier compatible)"""
        try:
            import time
            start = time.time()
            url = "http://api.aviationstack.com/v1/flights"
            params = {
                'access_key': self.api_key,
                'dep_iata': airport_code,
                'limit': 100
            }
            
            response = requests.get(url, params=params, timeout=10)
            duration_ms = int((time.time() - start) * 1000)
            data = response.json()
            
            tracker.record_aviationstack(
                endpoint=f"flights?dep_iata={airport_code}",
                duration_ms=duration_ms,
            )
            
            if 'data' in data:
                delays = []
                for flight in data['data']:
                    # Filter client-side for delayed flights
                    delay_min = flight.get('departure', {}).get('delay')
                    status = flight.get('flight_status', '')
                    
                    # Include if status is delayed/active or has delay minutes > 0
                    if status in ('delayed', 'active', 'diverted') or (delay_min and delay_min > 0):
                        scheduled = flight.get('departure', {}).get('scheduled', '')
                        actual = flight.get('departure', {}).get('actual') or flight.get('departure', {}).get('estimated', '')
                        
                        delays.append({
                            'flight_number': flight.get('flight', {}).get('iata', 'Unknown'),
                            'airline': flight.get('airline', {}).get('name', 'Unknown'),
                            'departure_airport': flight.get('departure', {}).get('iata', ''),
                            'arrival_airport': flight.get('arrival', {}).get('iata', ''),
                            'scheduled_departure': scheduled,
                            'actual_departure': actual or scheduled,
                            'delay_minutes': delay_min or 0,
                            'status': status,
                            'terminal': flight.get('departure', {}).get('terminal', ''),
                            'gate': flight.get('departure', {}).get('gate', '')
                        })
                
                # Sort by scheduled departure
                delays.sort(key=lambda x: x.get('scheduled_departure', ''))
                return delays
        
            # A 200 with no 'data' key means the provider refused the query.
            self.last_error = (
                f"AviationStack returned no flight data for {airport_code}: "
                f"{data.get('error') or 'unexpected response shape'}"
            )
            return []

        except Exception as e:
            tracker.record_aviationstack(
                endpoint=f"flights?dep_iata={airport_code}",
                status="error",
            )
            logger.warning("AviationStack error for %s: %s", airport_code, e)
            self.last_error = f'AviationStack request failed: {e}'
            return []
    
    @staticmethod
    def _calculate_delay(scheduled: str, actual: str) -> int:
        """Calculate delay in minutes"""
        if not scheduled or not actual:
            return 0
        
        try:
            sched_dt = datetime.fromisoformat(scheduled.replace('Z', '+00:00'))
            actual_dt = datetime.fromisoformat(actual.replace('Z', '+00:00'))
            delta = (actual_dt - sched_dt).total_seconds() / 60
            return max(0, int(delta))
        except:
            return 0
    
    def get_flight_status(
        self,
        flight_number: str,
        date: str
    ) -> Optional[Dict[str, Any]]:
        """Get status for a specific flight"""
        
        if self.api_key:
            try:
                url = "http://api.aviationstack.com/v1/flights"
                params = {
                    'access_key': self.api_key,
                    'flight_iata': flight_number,
                    'date': date
                }
                
                response = requests.get(url, params=params, timeout=10)
                data = response.json()
                
                if 'data' in data and data['data']:
                    flight = data['data'][0]
                    return {
                        'flight_number': flight_number,
                        'status': flight.get('flight_status', 'unknown'),
                        'scheduled_departure': flight.get('departure', {}).get('scheduled', ''),
                        'actual_departure': flight.get('departure', {}).get('actual', ''),
                        'delay_minutes': self._calculate_delay(
                            flight.get('departure', {}).get('scheduled'),
                            flight.get('departure', {}).get('actual')
                        )
                    }
            except:
                pass
        
        return None
