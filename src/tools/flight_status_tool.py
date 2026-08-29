"""FlightStatusTool — wraps FlightStatusService for the tool registry.

Capabilities: check_delays, find_nearby_airports
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from .base import ToolBase, ToolCapability, ToolError, ToolResult, ToolStatus
from ..agent.flight_status import FlightStatusService, LocationService

logger = logging.getLogger(__name__)


class FlightStatusTool(ToolBase):
    """Check flight delays and find nearby airports."""
    
    def __init__(self):
        self._service = FlightStatusService()
    
    @property
    def name(self) -> str:
        return 'flight_status'
    
    @property
    def description(self) -> str:
        return 'Check flight delays and find nearby airports'
    
    @property
    def capabilities(self) -> List[ToolCapability]:
        return [
            ToolCapability(
                name='check_delays',
                description='Get delayed flights departing from an airport',
                parameters={
                    'airport_code': 'IATA airport code (e.g. KUL)',
                    'days': 'Number of days to look ahead (default 3)',
                },
                returns='list[DelayedFlight]',
            ),
            ToolCapability(
                name='find_nearby_airports',
                description='Find airports near given coordinates',
                parameters={
                    'lat': 'Latitude',
                    'lon': 'Longitude',
                    'radius_km': 'Search radius in km (default 100)',
                },
                returns='list[Airport]',
            ),
        ]
    
    def execute(self, capability: str, params: Dict[str, Any]) -> ToolResult:
        if capability == 'check_delays':
            return self._check_delays(params)
        elif capability == 'find_nearby_airports':
            return self._find_nearby_airports(params)
        else:
            raise ToolError(
                f"Unknown capability: {capability}",
                tool_name=self.name,
                capability=capability,
            )
    
    def _check_delays(self, params: Dict[str, Any]) -> ToolResult:
        airport_code = params.get('airport_code', '')
        days = params.get('days', 3)
        
        if not airport_code:
            return ToolResult(
                status=ToolStatus.ERROR,
                message='airport_code is required',
                error='Missing parameter',
            )
        
        try:
            delays = self._service.get_delays_from_airport(airport_code, days)
            
            if not delays:
                return ToolResult(
                    status=ToolStatus.NO_RESULTS,
                    message=f'No delays found at {airport_code}',
                    data={'airport': airport_code, 'delays': []},
                )
            
            return ToolResult(
                status=ToolStatus.SUCCESS,
                data={
                    'airport': airport_code,
                    'delays': delays,
                    'count': len(delays),
                },
                message=f'Found {len(delays)} delayed flights at {airport_code}',
            )
            
        except Exception as e:
            return ToolResult(
                status=ToolStatus.ERROR,
                message=f'Failed to check delays: {str(e)}',
                error='DELAY_CHECK_FAILED',
            )
    
    def _find_nearby_airports(self, params: Dict[str, Any]) -> ToolResult:
        lat = params.get('lat')
        lon = params.get('lon')
        radius = params.get('radius_km', 100)
        
        if lat is None or lon is None:
            return ToolResult(
                status=ToolStatus.ERROR,
                message='lat and lon are required',
                error='Missing parameters',
            )
        
        try:
            airports = LocationService.find_nearby_airports(float(lat), float(lon), int(radius))
            
            if not airports:
                return ToolResult(
                    status=ToolStatus.NO_RESULTS,
                    message=f'No airports found within {radius}km',
                    data={'airports': []},
                )
            
            return ToolResult(
                status=ToolStatus.SUCCESS,
                data={'airports': airports},
                message=f'Found {len(airports)} airports nearby',
            )
            
        except Exception as e:
            return ToolResult(
                status=ToolStatus.ERROR,
                message=f'Failed to find airports: {str(e)}',
                error='AIRPORT_SEARCH_FAILED',
            )


# Auto-register on import
from .registry import tool_registry
tool_registry.register(FlightStatusTool())
