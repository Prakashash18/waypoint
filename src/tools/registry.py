"""Tool Registry — discover and invoke tools by capability."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Type

from .base import ToolBase, ToolCapability, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Central registry for all agent tools.
    
    Tools register themselves on import. The agent queries the registry
    by capability name and executes the matching tool.
    
    Usage:
        from src.tools import tool_registry
        
        # Find tools that can search flights
        tools = tool_registry.find_tools('search_flights')
        
        # Execute
        result = tool_registry.execute('atlas_flights', 'search_flights', {...})
    """
    
    def __init__(self):
        self._tools: Dict[str, ToolBase] = {}
    
    def register(self, tool: ToolBase) -> None:
        """Register a tool instance."""
        if tool.name in self._tools:
            logger.warning(f"Tool '{tool.name}' already registered, replacing")
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name} ({tool.description})")
    
    def unregister(self, name: str) -> None:
        """Remove a tool from the registry."""
        self._tools.pop(name, None)
    
    def get(self, name: str) -> Optional[ToolBase]:
        """Get a tool by name."""
        return self._tools.get(name)
    
    def list_tools(self) -> List[ToolBase]:
        """Get all registered tools."""
        return list(self._tools.values())
    
    def find_tools(self, capability: str) -> List[ToolBase]:
        """Find all tools that support a given capability."""
        return [
            tool for tool in self._tools.values()
            if tool.has_capability(capability)
        ]
    
    def all_capabilities(self) -> Dict[str, List[str]]:
        """Map capability names to tool names that support them."""
        caps: Dict[str, List[str]] = {}
        for tool in self._tools.values():
            for cap in tool.capabilities:
                caps.setdefault(cap.name, []).append(tool.name)
        return caps
    
    def execute(self, tool_name: str, capability: str, params: Dict[str, Any]) -> ToolResult:
        """Execute a specific capability on a specific tool.
        
        Args:
            tool_name: Name of the tool (e.g. 'atlas_flights')
            capability: Capability to invoke (e.g. 'search_flights')
            params: Parameters for the capability
            
        Returns:
            ToolResult
            
        Raises:
            ToolError if tool not found or capability not supported
        """
        tool = self._tools.get(tool_name)
        if not tool:
            from .base import ToolError
            raise ToolError(
                f"Tool '{tool_name}' not found in registry",
                tool_name=tool_name,
                capability=capability,
            )
        
        if not tool.has_capability(capability):
            from .base import ToolError
            raise ToolError(
                f"Tool '{tool_name}' does not support '{capability}'",
                tool_name=tool_name,
                capability=capability,
            )
        
        return tool.execute(capability, params)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize the full registry for API/UI display."""
        return {
            'tools': [tool.to_dict() for tool in self._tools.values()],
            'capabilities': self.all_capabilities(),
        }


# Global singleton — tools register themselves here on import
tool_registry = ToolRegistry()
