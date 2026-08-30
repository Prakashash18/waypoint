"""IATA airline codes to names.

Atlas returns only the two-character carrier code — "TR282" tells a traveller
nothing about who they are flying with. This is the reference table that turns
it into "Scoot".

The thirteen carriers the Atlas sandbox actually serves are all here; the rest
is broad coverage of carriers a traveller in this region might meet. An unknown
code falls back to the code itself rather than a guess.
"""

from __future__ import annotations

from typing import Optional

AIRLINES = {
    # ── seen in Atlas sandbox results ─────────────────────────────
    'TR': 'Scoot',
    'AK': 'AirAsia',
    'OD': 'Batik Air Malaysia',
    '8B': 'TransNusa',
    '7C': 'Jeju Air',
    'FD': 'Thai AirAsia',
    'DD': 'Nok Air',
    'ID': 'Batik Air Indonesia',
    'JT': 'Lion Air',
    'QZ': 'Indonesia AirAsia',
    'VJ': 'VietJet Air',
    'VZ': 'Thai VietJet Air',
    'ZG': 'Zipair',
    # ── Southeast Asia ────────────────────────────────────────────
    'SQ': 'Singapore Airlines',
    'MH': 'Malaysia Airlines',
    'GA': 'Garuda Indonesia',
    'TG': 'Thai Airways',
    'PR': 'Philippine Airlines',
    '5J': 'Cebu Pacific',
    'VN': 'Vietnam Airlines',
    'BR': 'EVA Air',
    'CI': 'China Airlines',
    'SL': 'Thai Lion Air',
    'MI': 'Scoot (SilkAir)',
    'BI': 'Royal Brunei',
    'K6': 'Cambodia Angkor Air',
    'UL': 'SriLankan Airlines',
    '3K': 'Jetstar Asia',
    'XJ': 'Thai AirAsia X',
    'D7': 'AirAsia X',
    'SJ': 'Sriwijaya Air',
    'IU': 'Super Air Jet',
    # ── East and South Asia ───────────────────────────────────────
    'CX': 'Cathay Pacific',
    'HX': 'Hong Kong Airlines',
    'JL': 'Japan Airlines',
    'NH': 'All Nippon Airways',
    'KE': 'Korean Air',
    'OZ': 'Asiana Airlines',
    'CA': 'Air China',
    'MU': 'China Eastern',
    'CZ': 'China Southern',
    'AI': 'Air India',
    '6E': 'IndiGo',
    'UK': 'Vistara',
    'SG': 'SpiceJet',
    'PG': 'Bangkok Airways',
    'MM': 'Peach Aviation',
    'GK': 'Jetstar Japan',
    'TW': "T'way Air",
    'LJ': 'Jin Air',
    'BX': 'Air Busan',
    # ── Middle East ───────────────────────────────────────────────
    'EK': 'Emirates',
    'QR': 'Qatar Airways',
    'EY': 'Etihad Airways',
    'SV': 'Saudia',
    'GF': 'Gulf Air',
    'WY': 'Oman Air',
    'TK': 'Turkish Airlines',
    'FZ': 'flydubai',
    # ── Europe ────────────────────────────────────────────────────
    'BA': 'British Airways',
    'LH': 'Lufthansa',
    'AF': 'Air France',
    'KL': 'KLM',
    'IB': 'Iberia',
    'AZ': 'ITA Airways',
    'LX': 'SWISS',
    'OS': 'Austrian Airlines',
    'SK': 'SAS',
    'AY': 'Finnair',
    'TP': 'TAP Air Portugal',
    'FR': 'Ryanair',
    'U2': 'easyJet',
    'W6': 'Wizz Air',
    'VS': 'Virgin Atlantic',
    'EI': 'Aer Lingus',
    'LO': 'LOT Polish Airlines',
    # ── Americas ──────────────────────────────────────────────────
    'AA': 'American Airlines',
    'UA': 'United Airlines',
    'DL': 'Delta Air Lines',
    'WN': 'Southwest Airlines',
    'B6': 'JetBlue',
    'AS': 'Alaska Airlines',
    'AC': 'Air Canada',
    'WS': 'WestJet',
    'AM': 'Aeroméxico',
    'LA': 'LATAM Airlines',
    'AV': 'Avianca',
    'CM': 'Copa Airlines',
    'G3': 'Gol',
    'AD': 'Azul',
    # ── Oceania and Africa ────────────────────────────────────────
    'QF': 'Qantas',
    'VA': 'Virgin Australia',
    'JQ': 'Jetstar',
    'NZ': 'Air New Zealand',
    'FJ': 'Fiji Airways',
    'SA': 'South African Airways',
    'ET': 'Ethiopian Airlines',
    'KQ': 'Kenya Airways',
    'MS': 'EgyptAir',
    'AT': 'Royal Air Maroc',
}


def name_for(code: Optional[str]) -> str:
    """Airline name for a carrier code, or the code itself if unknown.

    Returning the code beats inventing a name: "TR" at least matches what is
    printed on the ticket.
    """
    if not code:
        return ''
    return AIRLINES.get(code.strip().upper(), code.strip().upper())
