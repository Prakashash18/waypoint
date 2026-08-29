"""Base classes for all tools in the registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ToolStatus(str, Enum):
    """Result status from a tool call."""
    SUCCESS = 'success'
    ERROR = 'error'
    PARTIAL = 'partial'  # Some results, some failures
    NO_RESULTS = 'no_results'


@dataclass
class ToolResult:
    """Standardized result from any tool call.
    
    Every tool returns this shape so the agent can reason about
    results uniformly regardless of which tool produced them.
    """
    status: ToolStatus
    data: Any = None                    # Tool-specific payload
    message: str = ''
    error: Optional[str] = None
    raw_response: Optional[Dict] = None # For debugging
    
    def is_success(self) -> bool:
        return self.status == ToolStatus.SUCCESS
    
    def is_error(self) -> bool:
        return self.status == ToolStatus.ERROR
    
    def has_data(self) -> bool:
        return self.data is not None and self.data != [] and self.data != {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'status': self.status.value,
            'data': self.data,
            'message': self.message,
            'error': self.error,
        }


class ToolError(Exception):
    """Base exception for tool failures."""
    
    def __init__(
        self,
        message: str,
        tool_name: str = '',
        capability: str = '',
        retryable: bool = False,
        raw_error: Optional[str] = None
    ):
        super().__init__(message)
        self.tool_name = tool_name
        self.capability = capability
        self.retryable = retryable
        self.raw_error = raw_error


@dataclass
class ToolCapability:
    """Describes one thing a tool can do."""
    name: str                           # e.g. "search_flights"
    description: str                    # Human-readable description
    parameters: Dict[str, Any] = field(default_factory=dict)  # JSON schema of params
    returns: str = 'list'               # What kind of data comes back
    # Parameters the capability cannot run without. These are marked required
    # in the schema the model sees; leaving everything optional let it call
    # tools with no arguments and then report a dead end to the traveller.
    required: List[str] = field(default_factory=list)


class ToolBase(ABC):
    """Abstract base class for all registry tools.
    
    Every tool must:
    1. Declare its name, description, and capabilities
    2. Implement execute() for each capability
    3. Return ToolResult from every call
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier, e.g. 'atlas_flights'."""
        ...
    
    @property
    @abstractmethod
    def description(self) -> str:
        """One-line human description, e.g. 'Search and book flights'."""
        ...
    
    @property
    @abstractmethod
    def capabilities(self) -> List[ToolCapability]:
        """List of what this tool can do."""
        ...
    
    @abstractmethod
    def execute(self, capability: str, params: Dict[str, Any]) -> ToolResult:
        """Execute a capability with given parameters.
        
        Args:
            capability: Which capability to invoke (e.g. 'search_flights')
            params: Parameters for that capability
            
        Returns:
            ToolResult with status and data
            
        Raises:
            ToolError if the capability is not supported or execution fails
        """
        ...
    
    def has_capability(self, capability: str) -> bool:
        """Check if this tool supports a given capability."""
        return capability in [c.name for c in self.capabilities]
    
    def get_capability(self, capability: str) -> Optional[ToolCapability]:
        """Get the ToolCapability descriptor by name."""
        for cap in self.capabilities:
            if cap.name == capability:
                return cap
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize tool metadata for the registry."""
        return {
            'name': self.name,
            'description': self.description,
            'capabilities': [
                {
                    'name': c.name,
                    'description': c.description,
                    'parameters': c.parameters,
                    'required': c.required,
                    'returns': c.returns,
                }
                for c in self.capabilities
            ],
        }
