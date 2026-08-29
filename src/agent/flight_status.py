"""
Flight Status and Location Services
Provides real-time flight delay information and location-based airport detection
"""

import requests
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import os
from .api_tracker import tracker


class LocationService:
    """Detect user location and find nearby airports"""
    
    # Major airports with their coordinates
    AIRPORT_DATABASE = {
        'KUL': {'name': 'Kuala Lumpur International', 'lat': 2.7456, 'lon': 101.7099, 'city': 'Kuala Lumpur'},
        'SIN': {'name': 'Singapore Changi', 'lat': 1.3644, 'lon': 103.9915, 'city': 'Singapore'},
        'BKK': {'name': 'Bangkok Suvarnabhumi', 'lat': 13.6900, 'lon': 100.7501, 'city': 'Bangkok'},
        'HKG': {'name': 'Hong Kong International', 'lat': 22.3080, 'lon': 113.9185, 'city': 'Hong Kong'},
        'NRT': {'name': 'Tokyo Narita', 'lat': 35.7647, 'lon': 140.3864, 'city': 'Tokyo'},
        'ICN': {'name': 'Seoul Incheon', 'lat': 37.4602, 'lon': 126.4407, 'city': 'Seoul'},
        'JFK': {'name': 'New York JFK', 'lat': 40.6413, 'lon': -73.7781, 'city': 'New York'},
        'LAX': {'name': 'Los Angeles International', 'lat': 33.9425, 'lon': -118.4081, 'city': 'Los Angeles'},
        'LHR': {'name': 'London Heathrow', 'lat': 51.4700, 'lon': -0.4543, 'city': 'London'},
        'CDG': {'name': 'Paris Charles de Gaulle', 'lat': 49.0097, 'lon': 2.5479, 'city': 'Paris'},
    }
    
    @classmethod
    def find_nearby_airports(cls, lat: float, lon: float, radius_km: int = 100) -> List[Dict[str, Any]]:
        """Find airports within radius of given coordinates"""
        nearby = []
        
        for code, airport in cls.AIRPORT_DATABASE.items():
            distance = cls._haversine_distance(lat, lon, airport['lat'], airport['lon'])
            if distance <= radius_km:
                nearby.append({
                    'code': code,
                    'name': airport['name'],
                    'city': airport['city'],
                    'distance_km': round(distance, 1)
                })
        
        # Sort by distance
        nearby.sort(key=lambda x: x['distance_km'])
        return nearby
    
    @classmethod
    def get_airport_by_ip(cls, ip: str = None) -> Optional[Dict[str, Any]]:
        """Get nearest airport based on IP geolocation"""
        try:
            # Use free IP geolocation API
            if ip:
                url = f"http://ip-api.com/json/{ip}"
            else:
                url = "http://ip-api.com/json"
            
            response = requests.get(url, timeout=5)
            data = response.json()
            
            if data.get('status') == 'success':
                lat = data['lat']
                lon = data['lon']
                
                # Find nearest airport
                nearby = cls.find_nearby_airports(lat, lon, radius_km=200)
                if nearby:
                    return nearby[0]
                
                # Return location info even if no airport found
                return {
                    'city': data.get('city', 'Unknown'),
                    'country': data.get('country', 'Unknown'),
                    'lat': lat,
                    'lon': lon
                }
        except Exception:
            pass
        
        return None
    
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
    
    def get_delays_from_airport(
        self,
        airport_code: str,
        days: int = 3
    ) -> List[Dict[str, Any]]:
        """Get delayed flights from an airport for the next N days"""
        
        # Check simulate toggle first
        if tracker.simulate_delays:
            return self._get_simulated_delays(airport_code, days)
        
        # Try real API first
        if self.api_key:
            return self._get_delays_from_api(airport_code, days)
        else:
            # Return simulated data for demo
            return self._get_simulated_delays(airport_code, days)
    
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
        
        except Exception as e:
            tracker.record_aviationstack(
                endpoint=f"flights?dep_iata={airport_code}",
                status="error",
            )
            print(f"AviationStack API error: {e}")
        
        # Fall back to simulated data on any error
        return self._get_simulated_delays(airport_code, days)
    
    def _get_simulated_delays(
        self,
        airport_code: str,
        days: int
    ) -> List[Dict[str, Any]]:
        """
        Generate SIMULATED delay data for demo purposes.
        
        WARNING: This is NOT real flight data. It is randomly generated
        for demonstration only. To get real delays, add an AviationStack
        or FlightAware API key to .env.
        
        Uses routes known to exist in the Atlas CLI sandbox.
        """
        import random
        
        # Routes that Atlas CLI sandbox actually serves
        routes = {
            'KUL': ['SIN', 'BKK', 'PEN', 'LGK', 'JHB', 'KCH', 'BKI'],
            'SIN': ['KUL', 'BKK', 'PEN', 'HKG', 'DPS'],
            'BKK': ['KUL', 'SIN', 'CNX', 'HKT', 'PEN'],
        }
        
        airlines_with_codes = [
            ('AirAsia', 'AK'),
            ('Malaysia Airlines', 'MH'),
            ('Singapore Airlines', 'SQ'),
            ('Scoot', 'TR'),
            ('Jetstar', '3K'),
        ]
        
        available_dests = routes.get(airport_code, ['SIN', 'BKK', 'PEN', 'HKG'])
        
        delays = []
        now = datetime.utcnow()
        
        # Start from TOMORROW to ensure Atlas CLI has flights for the date
        for day in range(1, days + 1):
            date = now + timedelta(days=day)
            
            # Generate 5-10 delayed flights per day
            num_delays = random.randint(5, 10)
            
            for i in range(num_delays):
                hour = random.randint(6, 22)
                minute = random.choice([0, 15, 30, 45])
                scheduled = date.replace(hour=hour, minute=minute, second=0)
                
                delay_minutes = random.choice([15, 30, 45, 60, 90, 120, 180])
                actual = scheduled + timedelta(minutes=delay_minutes)
                
                destination = random.choice(available_dests)
                airline_name, airline_code = random.choice(airlines_with_codes)
                flight_num = f"{airline_code}{random.randint(100, 999)}"
                
                delays.append({
                    'flight_number': flight_num,
                    'airline': airline_name,
                    'departure_airport': airport_code,
                    'arrival_airport': destination,
                    'scheduled_departure': scheduled.isoformat() + 'Z',
                    'actual_departure': actual.isoformat() + 'Z',
                    'delay_minutes': delay_minutes,
                    'status': 'delayed',
                    'terminal': f"T{random.randint(1, 2)}",
                    'gate': f"{random.choice(['A', 'B', 'C', 'D'])}{random.randint(1, 20)}"
                })
        
        # Sort by scheduled departure
        delays.sort(key=lambda x: x['scheduled_departure'])
        return delays
    
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
