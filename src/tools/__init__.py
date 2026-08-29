"""Tool Registry — the capabilities the trip agent can reach for.

Each tool implements ToolBase and registers itself with the global
ToolRegistry on import. The agent discovers tools by capability, not by name,
so adding a provider is an import away.

Every tool returns records carrying `provenance`. There is deliberately no
simulated data provider: when a source fails the tool reports the failure and
the agent tells the user, rather than inventing a plausible answer.
"""

from .base import ToolBase, ToolResult, ToolError, ToolStatus, ToolCapability
from .provenance import Provenance, SourceReport, SourceStatus, stamp
from .registry import ToolRegistry, tool_registry

from .atlas_tool import AtlasTool
from .flight_status_tool import FlightStatusTool
from .places_tool import PlacesTool
from .hotel_rates_tool import HotelRatesTool
from .imagery_tool import ImageryTool

# Tools that do not self-register on import are registered here, once.
for _tool in (PlacesTool(), HotelRatesTool(), ImageryTool()):
    if not tool_registry.get(_tool.name):
        tool_registry.register(_tool)

__all__ = [
    'ToolBase', 'ToolResult', 'ToolError', 'ToolStatus', 'ToolCapability',
    'Provenance', 'SourceReport', 'SourceStatus', 'stamp',
    'ToolRegistry', 'tool_registry',
    'AtlasTool', 'FlightStatusTool', 'PlacesTool', 'HotelRatesTool', 'ImageryTool',
]
