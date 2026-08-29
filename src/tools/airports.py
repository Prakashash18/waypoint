"""A bundled reference of major passenger airports.

Overpass is the richer source but it rate-limits and times out, and "which
airport am I flying from" sits on the critical path of every search. These are
real airports with real coordinates, used when Overpass cannot answer in time.
Records carry a provenance of 'builtin' so the UI never implies a live lookup.

Coordinates are the published airport reference points, to 3 decimal places
(~100 m), which is far finer than any nearest-airport decision needs.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

# iata, name, city, lat, lon
_ROWS = [
    # ── Southeast Asia ────────────────────────────────────────────
    ('KUL', 'Kuala Lumpur International', 'Kuala Lumpur', 2.746, 101.710),
    ('SIN', 'Singapore Changi', 'Singapore', 1.364, 103.991),
    ('BKK', 'Suvarnabhumi', 'Bangkok', 13.690, 100.750),
    ('DMK', 'Don Mueang', 'Bangkok', 13.912, 100.607),
    ('DPS', 'Ngurah Rai', 'Denpasar', -8.748, 115.167),
    ('CGK', 'Soekarno-Hatta', 'Jakarta', -6.126, 106.656),
    ('PEN', 'Penang International', 'Penang', 5.297, 100.277),
    ('HKT', 'Phuket International', 'Phuket', 8.113, 98.317),
    ('CNX', 'Chiang Mai International', 'Chiang Mai', 18.767, 98.963),
    ('SGN', 'Tan Son Nhat', 'Ho Chi Minh City', 10.819, 106.652),
    ('HAN', 'Noi Bai', 'Hanoi', 21.221, 105.807),
    ('MNL', 'Ninoy Aquino', 'Manila', 14.509, 121.020),
    ('CEB', 'Mactan-Cebu', 'Cebu', 10.308, 123.979),
    ('RGN', 'Yangon International', 'Yangon', 16.907, 96.133),
    ('PNH', 'Phnom Penh International', 'Phnom Penh', 11.546, 104.844),
    ('REP', 'Siem Reap Angkor', 'Siem Reap', 13.411, 103.813),
    ('BKI', 'Kota Kinabalu', 'Kota Kinabalu', 5.937, 116.051),
    ('JHB', 'Senai International', 'Johor Bahru', 1.641, 103.670),
    ('LGK', 'Langkawi International', 'Langkawi', 6.330, 99.729),
    ('SUB', 'Juanda', 'Surabaya', -7.380, 112.787),
    # ── East Asia ─────────────────────────────────────────────────
    ('HKG', 'Hong Kong International', 'Hong Kong', 22.308, 113.919),
    ('NRT', 'Narita International', 'Tokyo', 35.765, 140.386),
    ('HND', 'Haneda', 'Tokyo', 35.549, 139.780),
    ('KIX', 'Kansai International', 'Osaka', 34.427, 135.244),
    ('ICN', 'Incheon International', 'Seoul', 37.460, 126.441),
    ('GMP', 'Gimpo International', 'Seoul', 37.558, 126.791),
    ('TPE', 'Taoyuan International', 'Taipei', 25.078, 121.233),
    ('PEK', 'Beijing Capital', 'Beijing', 40.080, 116.585),
    ('PKX', 'Beijing Daxing', 'Beijing', 39.509, 116.411),
    ('PVG', 'Shanghai Pudong', 'Shanghai', 31.143, 121.805),
    ('CAN', 'Guangzhou Baiyun', 'Guangzhou', 23.392, 113.299),
    ('SZX', 'Shenzhen Baoan', 'Shenzhen', 22.639, 113.811),
    ('MFM', 'Macau International', 'Macau', 22.150, 113.592),
    # ── South and Central Asia ────────────────────────────────────
    ('DEL', 'Indira Gandhi International', 'Delhi', 28.556, 77.100),
    ('BOM', 'Chhatrapati Shivaji', 'Mumbai', 19.089, 72.868),
    ('BLR', 'Kempegowda International', 'Bengaluru', 13.199, 77.710),
    ('MAA', 'Chennai International', 'Chennai', 12.994, 80.180),
    ('HYD', 'Rajiv Gandhi International', 'Hyderabad', 17.240, 78.429),
    ('CCU', 'Netaji Subhas Chandra Bose', 'Kolkata', 22.655, 88.447),
    ('CMB', 'Bandaranaike International', 'Colombo', 7.181, 79.884),
    ('MLE', 'Velana International', 'Male', 4.192, 73.529),
    ('KTM', 'Tribhuvan International', 'Kathmandu', 27.697, 85.359),
    ('DAC', 'Hazrat Shahjalal', 'Dhaka', 23.844, 90.398),
    ('KHI', 'Jinnah International', 'Karachi', 24.907, 67.161),
    ('ISB', 'Islamabad International', 'Islamabad', 33.549, 72.826),
    # ── Middle East ───────────────────────────────────────────────
    ('DXB', 'Dubai International', 'Dubai', 25.253, 55.365),
    ('AUH', 'Zayed International', 'Abu Dhabi', 24.433, 54.651),
    ('DOH', 'Hamad International', 'Doha', 25.273, 51.608),
    ('RUH', 'King Khalid International', 'Riyadh', 24.958, 46.699),
    ('JED', 'King Abdulaziz International', 'Jeddah', 21.680, 39.157),
    ('TLV', 'Ben Gurion', 'Tel Aviv', 32.011, 34.887),
    ('AMM', 'Queen Alia International', 'Amman', 31.723, 35.993),
    ('IST', 'Istanbul Airport', 'Istanbul', 41.262, 28.742),
    ('SAW', 'Sabiha Gokcen', 'Istanbul', 40.899, 29.309),
    # ── Europe ────────────────────────────────────────────────────
    ('LHR', 'Heathrow', 'London', 51.470, -0.454),
    ('LGW', 'Gatwick', 'London', 51.148, -0.190),
    ('STN', 'Stansted', 'London', 51.885, 0.235),
    ('MAN', 'Manchester', 'Manchester', 53.365, -2.273),
    ('EDI', 'Edinburgh', 'Edinburgh', 55.950, -3.372),
    ('DUB', 'Dublin', 'Dublin', 53.427, -6.244),
    ('CDG', 'Charles de Gaulle', 'Paris', 49.010, 2.548),
    ('ORY', 'Orly', 'Paris', 48.726, 2.365),
    ('AMS', 'Schiphol', 'Amsterdam', 52.311, 4.764),
    ('FRA', 'Frankfurt', 'Frankfurt', 50.033, 8.571),
    ('MUC', 'Munich', 'Munich', 48.354, 11.786),
    ('BER', 'Brandenburg', 'Berlin', 52.362, 13.501),
    ('MAD', 'Barajas', 'Madrid', 40.472, -3.561),
    ('BCN', 'El Prat', 'Barcelona', 41.297, 2.078),
    ('LIS', 'Humberto Delgado', 'Lisbon', 38.774, -9.134),
    ('OPO', 'Francisco Sa Carneiro', 'Porto', 41.248, -8.681),
    ('FCO', 'Fiumicino', 'Rome', 41.800, 12.239),
    ('MXP', 'Malpensa', 'Milan', 45.630, 8.723),
    ('VIE', 'Vienna International', 'Vienna', 48.110, 16.570),
    ('ZRH', 'Zurich', 'Zurich', 47.458, 8.548),
    ('GVA', 'Geneva', 'Geneva', 46.238, 6.109),
    ('BRU', 'Brussels', 'Brussels', 50.901, 4.484),
    ('CPH', 'Copenhagen Kastrup', 'Copenhagen', 55.618, 12.656),
    ('ARN', 'Arlanda', 'Stockholm', 59.650, 17.919),
    ('OSL', 'Gardermoen', 'Oslo', 60.194, 11.100),
    ('HEL', 'Helsinki-Vantaa', 'Helsinki', 60.317, 24.963),
    ('WAW', 'Chopin', 'Warsaw', 52.166, 20.967),
    ('PRG', 'Vaclav Havel', 'Prague', 50.101, 14.260),
    ('BUD', 'Ferenc Liszt', 'Budapest', 47.437, 19.256),
    ('ATH', 'Eleftherios Venizelos', 'Athens', 37.936, 23.947),
    ('KEF', 'Keflavik', 'Reykjavik', 63.985, -22.605),
    # ── North America ─────────────────────────────────────────────
    ('JFK', 'John F. Kennedy International', 'New York', 40.641, -73.778),
    ('EWR', 'Newark Liberty', 'New York', 40.690, -74.177),
    ('LGA', 'LaGuardia', 'New York', 40.777, -73.872),
    ('LAX', 'Los Angeles International', 'Los Angeles', 33.942, -118.408),
    ('SFO', 'San Francisco International', 'San Francisco', 37.619, -122.375),
    ('ORD', 'O Hare International', 'Chicago', 41.979, -87.904),
    ('ATL', 'Hartsfield-Jackson', 'Atlanta', 33.641, -84.427),
    ('DFW', 'Dallas/Fort Worth', 'Dallas', 32.900, -97.040),
    ('DEN', 'Denver International', 'Denver', 39.862, -104.673),
    ('SEA', 'Seattle-Tacoma', 'Seattle', 47.450, -122.309),
    ('MIA', 'Miami International', 'Miami', 25.796, -80.287),
    ('BOS', 'Logan International', 'Boston', 42.366, -71.020),
    ('IAH', 'George Bush Intercontinental', 'Houston', 29.990, -95.336),
    ('PHX', 'Sky Harbor', 'Phoenix', 33.435, -112.008),
    ('LAS', 'Harry Reid International', 'Las Vegas', 36.084, -115.154),
    ('HNL', 'Daniel K. Inouye', 'Honolulu', 21.319, -157.922),
    ('YYZ', 'Toronto Pearson', 'Toronto', 43.677, -79.631),
    ('YVR', 'Vancouver International', 'Vancouver', 49.194, -123.184),
    ('YUL', 'Montreal-Trudeau', 'Montreal', 45.458, -73.749),
    ('MEX', 'Benito Juarez', 'Mexico City', 19.436, -99.072),
    ('CUN', 'Cancun International', 'Cancun', 21.037, -86.877),
    # ── South America ─────────────────────────────────────────────
    ('GRU', 'Guarulhos', 'Sao Paulo', -23.435, -46.473),
    ('GIG', 'Galeao', 'Rio de Janeiro', -22.810, -43.251),
    ('EZE', 'Ministro Pistarini', 'Buenos Aires', -34.822, -58.536),
    ('SCL', 'Arturo Merino Benitez', 'Santiago', -33.393, -70.786),
    ('LIM', 'Jorge Chavez', 'Lima', -12.022, -77.114),
    ('BOG', 'El Dorado', 'Bogota', 4.702, -74.147),
    # ── Africa ────────────────────────────────────────────────────
    ('JNB', 'O. R. Tambo', 'Johannesburg', -26.139, 28.246),
    ('CPT', 'Cape Town International', 'Cape Town', -33.965, 18.602),
    ('CAI', 'Cairo International', 'Cairo', 30.122, 31.406),
    ('NBO', 'Jomo Kenyatta', 'Nairobi', -1.319, 36.928),
    ('LOS', 'Murtala Muhammed', 'Lagos', 6.577, 3.321),
    ('ADD', 'Bole International', 'Addis Ababa', 8.978, 38.799),
    ('CMN', 'Mohammed V', 'Casablanca', 33.367, -7.590),
    # ── Oceania ───────────────────────────────────────────────────
    ('SYD', 'Kingsford Smith', 'Sydney', -33.939, 151.175),
    ('MEL', 'Tullamarine', 'Melbourne', -37.669, 144.841),
    ('BNE', 'Brisbane', 'Brisbane', -27.384, 153.117),
    ('PER', 'Perth', 'Perth', -31.940, 115.967),
    ('AKL', 'Auckland', 'Auckland', -37.008, 174.792),
    ('CHC', 'Christchurch', 'Christchurch', -43.489, 172.532),
    ('NAN', 'Nadi International', 'Nadi', -17.755, 177.443),
]

AIRPORTS: List[Dict[str, Any]] = [
    {'iata': iata, 'name': name, 'city': city, 'lat': lat, 'lon': lon}
    for iata, name, city, lat, lon in _ROWS
]


def nearest(lat: float, lon: float, radius_km: float = 250,
            limit: int = 5) -> List[Dict[str, Any]]:
    """Airports within radius of a point, nearest first."""
    found = []
    for airport in AIRPORTS:
        dx = (math.radians(airport['lon'] - lon)
              * math.cos(math.radians((airport['lat'] + lat) / 2)) * 6371)
        dy = math.radians(airport['lat'] - lat) * 6371
        distance = math.hypot(dx, dy)
        if distance <= radius_km:
            found.append({**airport, 'distance_km': round(distance, 1),
                          'international': True, 'tier': 3})
    found.sort(key=lambda a: a['distance_km'])
    return found[:limit]
