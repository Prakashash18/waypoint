"""
Audit Trail
Append-only logging of all agent decisions and CLI interactions
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum
import json
import csv
import io


class AuditEventType(Enum):
    """Types of audit events"""
    SEARCH_INITIATED = "search_initiated"
    SEARCH_COMPLETED = "search_completed"
    OPTIONS_RANKED = "options_ranked"
    CHECKPOINT_PRESENTED = "checkpoint_presented"
    CHECKPOINT_APPROVED = "checkpoint_approved"
    CHECKPOINT_REJECTED = "checkpoint_rejected"
    CHECKPOINT_QUESTION = "checkpoint_question"
    CLI_COMMAND_EXECUTED = "cli_command_executed"
    CLI_RESPONSE_RECEIVED = "cli_response_received"
    PRICE_CHANGED = "price_changed"
    OFFER_VERIFIED = "offer_verified"
    BOOKING_CONFIRMED = "booking_confirmed"
    SEAT_ASSIGNED = "seat_assigned"
    BAGGAGE_ADDED = "baggage_added"
    ORDER_CREATED = "order_created"
    PAYMENT_INITIATED = "payment_initiated"
    PAYMENT_COMPLETED = "payment_completed"
    TICKET_ISSUED = "ticket_issued"
    ERROR_OCCURRED = "error_occurred"
    SESSION_STARTED = "session_started"
    SESSION_COMPLETED = "session_completed"


@dataclass
class AuditEvent:
    """Single audit event"""
    timestamp: datetime
    event_type: AuditEventType
    message: str
    request_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    checkpoint_id: Optional[str] = None
    cli_command: Optional[str] = None
    cli_response_code: Optional[str] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        d = asdict(self)
        d['timestamp'] = self.timestamp.isoformat()
        d['event_type'] = self.event_type.value
        return d
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AuditEvent':
        """Create from dictionary"""
        data = data.copy()
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        data['event_type'] = AuditEventType(data['event_type'])
        return cls(**data)


class AuditTrail:
    """Append-only audit trail for all agent operations"""
    
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or f"session_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        self.events: List[AuditEvent] = []
        self._log_event(
            AuditEventType.SESSION_STARTED,
            f"Audit session started: {self.session_id}"
        )
    
    def _log_event(
        self,
        event_type: AuditEventType,
        message: str,
        **kwargs
    ) -> AuditEvent:
        """Internal method to log an event"""
        event = AuditEvent(
            timestamp=datetime.utcnow(),
            event_type=event_type,
            message=message,
            **kwargs
        )
        self.events.append(event)
        return event
    
    def log_search(self, origin: str, destination: str, depart: str, request_id: Optional[str] = None):
        """Log search initiation"""
        return self._log_event(
            AuditEventType.SEARCH_INITIATED,
            f"Search initiated: {origin} → {destination} on {depart}",
            request_id=request_id,
            data={'origin': origin, 'destination': destination, 'depart': depart}
        )
    
    def log_search_completed(self, results_count: int, request_id: Optional[str] = None):
        """Log search completion"""
        return self._log_event(
            AuditEventType.SEARCH_COMPLETED,
            f"Search completed: {results_count} results found",
            request_id=request_id,
            data={'results_count': results_count}
        )
    
    def log_options_ranked(self, options: List[Dict[str, Any]]):
        """Log ranked options"""
        return self._log_event(
            AuditEventType.OPTIONS_RANKED,
            f"Options ranked: {len(options)} options",
            data={'options': options}
        )
    
    def log_checkpoint_presented(
        self,
        checkpoint_id: str,
        checkpoint_type: str,
        reasoning: str,
        cli_command: Optional[str] = None
    ):
        """Log checkpoint presentation"""
        return self._log_event(
            AuditEventType.CHECKPOINT_PRESENTED,
            f"Checkpoint presented: {checkpoint_type}",
            checkpoint_id=checkpoint_id,
            data={
                'checkpoint_type': checkpoint_type,
                'reasoning': reasoning
            },
            cli_command=cli_command
        )
    
    def log_checkpoint_approved(self, checkpoint_id: str, notes: Optional[str] = None):
        """Log checkpoint approval"""
        return self._log_event(
            AuditEventType.CHECKPOINT_APPROVED,
            f"Checkpoint approved: {checkpoint_id}",
            checkpoint_id=checkpoint_id,
            data={'notes': notes}
        )
    
    def log_checkpoint_rejected(self, checkpoint_id: str, reason: Optional[str] = None):
        """Log checkpoint rejection"""
        return self._log_event(
            AuditEventType.CHECKPOINT_REJECTED,
            f"Checkpoint rejected: {checkpoint_id}",
            checkpoint_id=checkpoint_id,
            data={'reason': reason}
        )
    
    def log_checkpoint_question(self, checkpoint_id: str, question: str):
        """Log checkpoint question"""
        return self._log_event(
            AuditEventType.CHECKPOINT_QUESTION,
            f"Question asked at checkpoint: {checkpoint_id}",
            checkpoint_id=checkpoint_id,
            data={'question': question}
        )
    
    def log_cli_command(self, command: str, request_id: Optional[str] = None):
        """Log CLI command execution"""
        return self._log_event(
            AuditEventType.CLI_COMMAND_EXECUTED,
            f"CLI command executed: {command}",
            request_id=request_id,
            cli_command=command
        )
    
    def log_cli_response(self, code: str, message: str, request_id: Optional[str] = None):
        """Log CLI response"""
        return self._log_event(
            AuditEventType.CLI_RESPONSE_RECEIVED,
            f"CLI response: {code} - {message}",
            request_id=request_id,
            cli_response_code=code
        )
    
    def log_price_change(
        self,
        original_price: float,
        new_price: float,
        currency: str,
        request_id: Optional[str] = None
    ):
        """Log price change"""
        return self._log_event(
            AuditEventType.PRICE_CHANGED,
            f"Price changed: {original_price} → {new_price} {currency}",
            request_id=request_id,
            data={
                'original_price': original_price,
                'new_price': new_price,
                'currency': currency,
                'price_diff': new_price - original_price
            }
        )
    
    def log_offer_verified(self, offer_id: str, request_id: Optional[str] = None):
        """Log offer verification"""
        return self._log_event(
            AuditEventType.OFFER_VERIFIED,
            f"Offer verified: {offer_id}",
            request_id=request_id,
            data={'offer_id': offer_id}
        )
    
    def log_booking_confirmed(self, booking_id: str, request_id: Optional[str] = None):
        """Log booking confirmation"""
        return self._log_event(
            AuditEventType.BOOKING_CONFIRMED,
            f"Booking confirmed: {booking_id}",
            request_id=request_id,
            data={'booking_id': booking_id}
        )
    
    def log_order_created(self, order_id: str, request_id: Optional[str] = None):
        """Log order creation"""
        return self._log_event(
            AuditEventType.ORDER_CREATED,
            f"Order created: {order_id}",
            request_id=request_id,
            data={'order_id': order_id}
        )
    
    def log_payment_completed(
        self,
        order_id: str,
        amount: float,
        currency: str,
        transaction_id: str,
        request_id: Optional[str] = None
    ):
        """Log payment completion"""
        return self._log_event(
            AuditEventType.PAYMENT_COMPLETED,
            f"Payment completed: {amount} {currency} for order {order_id}",
            request_id=request_id,
            data={
                'order_id': order_id,
                'amount': amount,
                'currency': currency,
                'transaction_id': transaction_id
            }
        )
    
    def log_ticket_issued(self, order_id: str, ticket_number: str, request_id: Optional[str] = None):
        """Log ticket issuance"""
        return self._log_event(
            AuditEventType.TICKET_ISSUED,
            f"Ticket issued: {ticket_number} for order {order_id}",
            request_id=request_id,
            data={'order_id': order_id, 'ticket_number': ticket_number}
        )
    
    def log_error(
        self,
        error: str,
        error_type: Optional[str] = None,
        retryable: bool = False,
        request_id: Optional[str] = None
    ):
        """Log error"""
        return self._log_event(
            AuditEventType.ERROR_OCCURRED,
            f"Error: {error}",
            request_id=request_id,
            data={
                'error': error,
                'error_type': error_type,
                'retryable': retryable
            }
        )
    
    def log_session_completed(self, success: bool, summary: str):
        """Log session completion"""
        return self._log_event(
            AuditEventType.SESSION_COMPLETED,
            f"Session completed: {summary}",
            data={'success': success, 'summary': summary}
        )
    
    def export_json(self) -> str:
        """Export audit trail as JSON"""
        return json.dumps({
            'session_id': self.session_id,
            'event_count': len(self.events),
            'events': [event.to_dict() for event in self.events]
        }, indent=2)
    
    def export_csv(self) -> str:
        """Export audit trail as CSV"""
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            'timestamp', 'event_type', 'message', 'request_id', 
            'checkpoint_id', 'cli_command', 'cli_response_code'
        ])
        writer.writeheader()
        
        for event in self.events:
            writer.writerow({
                'timestamp': event.timestamp.isoformat(),
                'event_type': event.event_type.value,
                'message': event.message,
                'request_id': event.request_id or '',
                'checkpoint_id': event.checkpoint_id or '',
                'cli_command': event.cli_command or '',
                'cli_response_code': event.cli_response_code or ''
            })
        
        return output.getvalue()
    
    def get_events_by_type(self, event_type: AuditEventType) -> List[AuditEvent]:
        """Get all events of a specific type"""
        return [e for e in self.events if e.event_type == event_type]
    
    def get_checkpoint_events(self, checkpoint_id: str) -> List[AuditEvent]:
        """Get all events for a specific checkpoint"""
        return [e for e in self.events if e.checkpoint_id == checkpoint_id]
