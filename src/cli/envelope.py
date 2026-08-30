"""
Atlas Flight CLI Envelope Parser
Parses the standard JSON envelope returned by all atlas-flight commands
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class AtlasEnvelope:
    """Standard JSON envelope from Atlas CLI"""
    schema_version: str
    status: str
    code: str
    message: str
    retryable: bool
    request_id: Optional[str]
    data: Dict[str, Any]
    details: Dict[str, Any]
    raw: Dict[str, Any]
    
    # Atlas answers with one of: success, action_required, terminal_error.
    # `terminal_error` was in none of the lists below, so a hard failure like
    # OFFER_EXPIRED read as neither a success nor an error — and callers that
    # branch on is_error() sailed past it and reported a green tick.
    ACTION_REQUIRED = 'action_required'

    def is_success(self) -> bool:
        """Check if the response indicates success"""
        return self.status == 'success' or self.code in ['SUCCESS', 'OK']

    def is_error(self) -> bool:
        """Anything that is neither a success nor a request for more input."""
        if self.is_success():
            return False
        return self.status != self.ACTION_REQUIRED

    def needs_input(self) -> bool:
        """Not failed — Atlas is waiting on something, like payment or details."""
        return self.status == self.ACTION_REQUIRED
    
    def is_retryable(self) -> bool:
        """Check if the error is retryable"""
        return self.retryable
    
    def get_data(self, key: str, default: Any = None) -> Any:
        """Get a value from the data field"""
        return self.data.get(key, default)
    
    def get_detail(self, key: str, default: Any = None) -> Any:
        """Get a value from the details field"""
        return self.details.get(key, default)


class EnvelopeParser:
    """Parser for Atlas CLI JSON envelope"""
    
    REQUIRED_FIELDS = ['schema_version', 'status', 'code', 'message', 'retryable', 'data']
    
    def parse(self, json_str: str) -> AtlasEnvelope:
        """Parse JSON string into AtlasEnvelope"""
        try:
            raw = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response: {e}")
        
        # Validate required fields
        missing = [f for f in self.REQUIRED_FIELDS if f not in raw]
        if missing:
            raise ValueError(f"Missing required fields in envelope: {missing}")
        
        return AtlasEnvelope(
            schema_version=raw['schema_version'],
            status=raw['status'],
            code=raw['code'],
            message=raw['message'],
            retryable=raw.get('retryable', False),
            request_id=raw.get('request_id'),
            data=raw.get('data', {}),
            details=raw.get('details', {}),
            raw=raw
        )
    
    def validate(self, envelope: AtlasEnvelope) -> bool:
        """Validate envelope structure"""
        return (
            envelope.schema_version is not None and
            envelope.status is not None and
            envelope.code is not None and
            envelope.message is not None
        )
