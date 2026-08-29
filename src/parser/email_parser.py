"""
Email Parser
Parses cancellation emails to extract itinerary details
"""

from typing import Dict, Any, Optional
import re
from datetime import datetime

from ..agent.reasoning import ReasoningEngine


class EmailParser:
    """Parses cancellation emails using Qwen or regex fallback"""
    
    # Common IATA airport codes pattern
    IATA_PATTERN = r'\b([A-Z]{3})\b'
    
    # Date patterns
    DATE_PATTERNS = [
        r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}',  # ISO format
        r'\d{1,2}/\d{1,2}/\d{4}',                  # MM/DD/YYYY
        r'\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}',  # 15 Sep 2026
    ]
    
    # PNR pattern (6 alphanumeric characters)
    PNR_PATTERN = r'\b([A-Z0-9]{6})\b'
    
    def __init__(self, reasoning_engine: Optional[ReasoningEngine] = None):
        self.reasoning = reasoning_engine or ReasoningEngine()
    
    def parse(self, email_text: str) -> Dict[str, Any]:
        """
        Parse a cancellation email and extract itinerary details.
        
        Tries Qwen first, falls back to regex extraction.
        """
        # Try AI-powered parsing first
        try:
            result = self.reasoning.parse_cancellation_email(email_text)
            if self._validate_result(result):
                return result
        except Exception:
            pass
        
        # Fall back to regex extraction
        return self._regex_parse(email_text)
    
    def _validate_result(self, result: Dict[str, Any]) -> bool:
        """Validate that extracted result has required fields"""
        required = ['origin', 'destination', 'original_departure']
        return all(field in result and result[field] for field in required)
    
    def _regex_parse(self, email_text: str) -> Dict[str, Any]:
        """Parse using regex patterns as fallback"""
        result = {
            'origin': '',
            'destination': '',
            'original_departure': '',
            'passengers': 1,
            'hard_deadline': None,
            'pnr': None,
            'notes': 'Extracted via regex'
        }
        
        # Extract IATA codes
        iata_codes = re.findall(self.IATA_PATTERN, email_text.upper())
        if len(iata_codes) >= 2:
            result['origin'] = iata_codes[0]
            result['destination'] = iata_codes[1]
        
        # Extract dates
        for pattern in self.DATE_PATTERNS:
            matches = re.findall(pattern, email_text, re.IGNORECASE)
            if matches:
                try:
                    # Try to parse the first match
                    date_str = matches[0]
                    
                    # Handle different formats
                    if 'T' in date_str:
                        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    elif '/' in date_str:
                        dt = datetime.strptime(date_str, '%m/%d/%Y')
                    else:
                        dt = datetime.strptime(date_str, '%d %b %Y')
                    
                    result['original_departure'] = dt.isoformat()
                    break
                except (ValueError, IndexError):
                    continue
        
        # Extract PNR
        pnr_matches = re.findall(self.PNR_PATTERN, email_text.upper())
        if pnr_matches:
            result['pnr'] = pnr_matches[0]
        
        # Extract passenger count (look for "passenger" or "pax" mentions)
        passenger_match = re.search(r'(\d+)\s+(?:passenger|pax|guest)', email_text, re.IGNORECASE)
        if passenger_match:
            result['passengers'] = int(passenger_match.group(1))
        
        return result
    
    def parse_pnr_json(self, pnr_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse a PNR-style JSON input into disruption format.
        
        Example input:
        {
            "pnr": "ABC123",
            "segments": [{
                "origin": "KUL",
                "destination": "SIN",
                "departure": "2026-09-15T08:00:00Z",
                "status": "cancelled"
            }],
            "passengers": 1
        }
        """
        segments = pnr_json.get('segments', [])
        
        if not segments:
            raise ValueError("No segments found in PNR data")
        
        # Find the cancelled segment
        cancelled = [s for s in segments if s.get('status', '').lower() == 'cancelled']
        
        if not cancelled:
            # Use the first segment if no cancelled one found
            segment = segments[0]
        else:
            segment = cancelled[0]
        
        return {
            'origin': segment.get('origin', ''),
            'destination': segment.get('destination', ''),
            'original_departure': segment.get('departure', ''),
            'passengers': pnr_json.get('passengers', 1),
            'hard_deadline': pnr_json.get('hard_deadline'),
            'pnr': pnr_json.get('pnr'),
            'notes': f"PNR: {pnr_json.get('pnr', 'N/A')}"
        }
