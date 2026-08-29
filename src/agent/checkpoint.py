"""
Checkpoint State Machine
Manages the four mandatory approval checkpoints in the booking flow
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable
from enum import Enum
import uuid
import json

from ..cli import AtlasCLI, AtlasEnvelope, PriceChangedError, SeatUnavailableError
from .search import RankedOption, DisruptedItinerary
from .audit import AuditTrail
from .reasoning import ReasoningEngine


class CheckpointType(Enum):
    """Types of checkpoints"""
    INITIAL_BOOKING = "initial_booking"
    PRICE_CHANGE = "price_change"
    SEAT_FALLBACK = "seat_fallback"
    FINAL_PAYMENT = "final_payment"


class BookingState(Enum):
    """States in the booking flow"""
    INTAKE = "intake"
    SEARCH = "search"
    OPTIONS_PRESENTED = "options_presented"
    CHECKPOINT_1_PENDING = "checkpoint_1_pending"
    OFFER_VERIFIED = "offer_verified"
    CHECKPOINT_2_PENDING = "checkpoint_2_pending"
    BOOKING_CONFIRMED = "booking_confirmed"
    CHECKPOINT_3_PENDING = "checkpoint_3_pending"
    PAYMENT_PENDING = "payment_pending"
    CHECKPOINT_4_PENDING = "checkpoint_4_pending"
    TICKET_ISSUED = "ticket_issued"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CheckpointDecision(Enum):
    """Possible checkpoint decisions"""
    APPROVE = "approve"
    REJECT = "reject"
    ASK_QUESTION = "ask_question"


@dataclass
class Checkpoint:
    """Represents a single checkpoint"""
    checkpoint_id: str
    checkpoint_type: CheckpointType
    title: str
    description: str
    reasoning: str
    what_changed: str
    cli_command: str
    context: Dict[str, Any]
    created_at: datetime = field(default_factory=datetime.utcnow)
    decision: Optional[CheckpointDecision] = None
    decision_notes: Optional[str] = None
    decided_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'checkpoint_id': self.checkpoint_id,
            'checkpoint_type': self.checkpoint_type.value,
            'title': self.title,
            'description': self.description,
            'reasoning': self.reasoning,
            'what_changed': self.what_changed,
            'cli_command': self.cli_command,
            'context': self.context,
            'created_at': self.created_at.isoformat(),
            'decision': self.decision.value if self.decision else None,
            'decision_notes': self.decision_notes,
            'decided_at': self.decided_at.isoformat() if self.decided_at else None
        }


class CheckpointManager:
    """Manages the checkpoint state machine for a booking flow"""
    
    def __init__(
        self,
        cli: AtlasCLI,
        audit: AuditTrail,
        reasoning: ReasoningEngine
    ):
        self.cli = cli
        self.audit = audit
        self.reasoning = reasoning
        self.state = BookingState.INTAKE
        self.checkpoints: List[Checkpoint] = []
        self.current_checkpoint: Optional[Checkpoint] = None
        self.itinerary: Optional[DisruptedItinerary] = None
        self.selected_option: Optional[RankedOption] = None
        self.booking_id: Optional[str] = None
        self.order_id: Optional[str] = None
        self.payment_confirmation_id: Optional[str] = None
        self.original_price: Optional[float] = None
        self.confirmed_price: Optional[float] = None
        self.ticket_number: Optional[str] = None
    
    def start_session(self, itinerary: DisruptedItinerary) -> List[RankedOption]:
        """Start a new booking session"""
        self.itinerary = itinerary
        self.state = BookingState.SEARCH
        
        # Search for options
        from .search import SearchEngine
        search_engine = SearchEngine(self.cli)
        options = search_engine.search(itinerary)
        
        # Generate tradeoffs
        self.reasoning.generate_tradeoffs(options, itinerary)
        
        self.state = BookingState.OPTIONS_PRESENTED
        
        # Log search
        self.audit.log_search(
            origin=itinerary.origin,
            destination=itinerary.destination,
            depart=itinerary.original_departure.strftime('%Y-%m-%d')
        )
        self.audit.log_search_completed(len(options))
        self.audit.log_options_ranked([opt.to_dict() for opt in options])
        
        return options
    
    def present_initial_booking_checkpoint(
        self,
        selected_option: RankedOption
    ) -> Checkpoint:
        """Present checkpoint 1: Initial booking authorization"""
        self.selected_option = selected_option
        self.original_price = selected_option.price
        
        checkpoint = Checkpoint(
            checkpoint_id=str(uuid.uuid4()),
            checkpoint_type=CheckpointType.INITIAL_BOOKING,
            title="Booking Authorization",
            description=f"Book flight {selected_option.airline} {selected_option.flight_number}",
            reasoning=self.reasoning.explain_checkpoint(
                'INITIAL_BOOKING',
                {'selected_option': selected_option.to_dict()}
            ),
            what_changed="Initial selection from ranked options",
            cli_command=f"atlas-flight offer verify --offer-id {selected_option.offer_id} --json",
            context={
                'option': selected_option.to_dict(),
                'itinerary': self.itinerary.to_dict()
            }
        )
        
        self.current_checkpoint = checkpoint
        self.checkpoints.append(checkpoint)
        self.state = BookingState.CHECKPOINT_1_PENDING
        
        self.audit.log_checkpoint_presented(
            checkpoint_id=checkpoint.checkpoint_id,
            checkpoint_type=checkpoint.checkpoint_type.value,
            reasoning=checkpoint.reasoning,
            cli_command=checkpoint.cli_command
        )
        
        return checkpoint
    
    def decide_checkpoint(
        self,
        checkpoint_id: str,
        decision: CheckpointDecision,
        notes: Optional[str] = None
    ) -> bool:
        """Process a checkpoint decision"""
        checkpoint = next((c for c in self.checkpoints if c.checkpoint_id == checkpoint_id), None)
        if not checkpoint:
            raise ValueError(f"Checkpoint {checkpoint_id} not found")
        
        checkpoint.decision = decision
        checkpoint.decision_notes = notes
        checkpoint.decided_at = datetime.utcnow()
        
        # Log decision
        if decision == CheckpointDecision.APPROVE:
            self.audit.log_checkpoint_approved(checkpoint_id, notes)
        elif decision == CheckpointDecision.REJECT:
            self.audit.log_checkpoint_rejected(checkpoint_id, notes)
        elif decision == CheckpointDecision.ASK_QUESTION:
            self.audit.log_checkpoint_question(checkpoint_id, notes or "")
        
        # Execute next step based on checkpoint type and decision
        if decision == CheckpointDecision.APPROVE:
            return self._execute_post_checkpoint(checkpoint)
        
        return False
    
    def _execute_post_checkpoint(self, checkpoint: Checkpoint) -> bool:
        """Execute actions after checkpoint approval"""
        
        if checkpoint.checkpoint_type == CheckpointType.INITIAL_BOOKING:
            # Verify offer
            try:
                verify_result = self.cli.offer_verify(self.selected_option.offer_id)
                self.audit.log_offer_verified(
                    self.selected_option.offer_id,
                    verify_result.request_id
                )
                
                if verify_result.is_success():
                    self.state = BookingState.OFFER_VERIFIED
                    # Proceed to confirm price
                    return self._confirm_price()
                else:
                    # Handle error
                    self.audit.log_error(
                        verify_result.message,
                        verify_result.code,
                        verify_result.retryable,
                        verify_result.request_id
                    )
                    return False
            
            except Exception as e:
                self.audit.log_error(str(e), type(e).__name__)
                return False
        
        elif checkpoint.checkpoint_type == CheckpointType.PRICE_CHANGE:
            # Proceed with confirmed price
            self.state = BookingState.BOOKING_CONFIRMED
            return self._proceed_to_seat_selection()
        
        elif checkpoint.checkpoint_type == CheckpointType.SEAT_FALLBACK:
            # Proceed to payment
            self.state = BookingState.PAYMENT_PENDING
            return self._present_final_payment_checkpoint()
        
        elif checkpoint.checkpoint_type == CheckpointType.FINAL_PAYMENT:
            # Execute payment
            return self._execute_payment()
        
        return False
    
    def _confirm_price(self) -> bool:
        """Confirm price and handle any changes"""
        try:
            price_result = self.cli.booking_confirm_price(self.selected_option.offer_id)
            
            if price_result.is_success():
                self.booking_id = price_result.get_data('booking_id')
                self.confirmed_price = price_result.get_data('price')
                
                self.audit.log_booking_confirmed(
                    self.booking_id,
                    price_result.request_id
                )
                
                # Check if price changed
                if self.confirmed_price != self.original_price:
                    # Present price change checkpoint
                    return self._present_price_change_checkpoint(
                        self.original_price,
                        self.confirmed_price,
                        price_result.get_data('currency', 'USD')
                    )
                else:
                    # Price unchanged, proceed
                    self.state = BookingState.BOOKING_CONFIRMED
                    return self._proceed_to_seat_selection()
            
            else:
                self.audit.log_error(
                    price_result.message,
                    price_result.code,
                    price_result.retryable,
                    price_result.request_id
                )
                return False
        
        except PriceChangedError as e:
            # Price changed, present checkpoint
            self.audit.log_price_change(
                e.original_price,
                e.new_price,
                e.currency,
                None
            )
            return self._present_price_change_checkpoint(
                e.original_price,
                e.new_price,
                e.currency
            )
        
        except Exception as e:
            self.audit.log_error(str(e), type(e).__name__)
            return False
    
    def _present_price_change_checkpoint(
        self,
        original_price: float,
        new_price: float,
        currency: str
    ) -> bool:
        """Present checkpoint 2: Price change acceptance"""
        checkpoint = Checkpoint(
            checkpoint_id=str(uuid.uuid4()),
            checkpoint_type=CheckpointType.PRICE_CHANGE,
            title="Price Change Confirmation",
            description=f"Price increased from {original_price:.2f} to {new_price:.2f} {currency}",
            reasoning=self.reasoning.explain_checkpoint(
                'PRICE_CHANGE',
                {
                    'original_price': original_price,
                    'new_price': new_price,
                    'currency': currency
                }
            ),
            what_changed=f"Price increased by {new_price - original_price:.2f} {currency}",
            cli_command=f"atlas-flight booking seat --booking-id {self.booking_id} --preference auto --json",
            context={
                'original_price': original_price,
                'new_price': new_price,
                'currency': currency,
                'booking_id': self.booking_id
            }
        )
        
        self.current_checkpoint = checkpoint
        self.checkpoints.append(checkpoint)
        self.state = BookingState.CHECKPOINT_2_PENDING
        
        self.audit.log_checkpoint_presented(
            checkpoint_id=checkpoint.checkpoint_id,
            checkpoint_type=checkpoint.checkpoint_type.value,
            reasoning=checkpoint.reasoning,
            cli_command=checkpoint.cli_command
        )
        
        return True
    
    def _proceed_to_seat_selection(self) -> bool:
        """Attempt seat selection"""
        try:
            seat_result = self.cli.booking_seat(self.booking_id, 'auto')
            
            if seat_result.is_success():
                self.audit._log_event(
                    self.audit.events.__class__.__bases__[0],
                    f"Seat assigned: {seat_result.get_data('seat_number')}",
                    data=seat_result.data
                )
                # Proceed to order creation
                return self._create_order()
            
            else:
                # Seat unavailable or other error
                self.audit.log_error(
                    seat_result.message,
                    seat_result.code,
                    seat_result.retryable,
                    seat_result.request_id
                )
                return False
        
        except SeatUnavailableError:
            # Present seat fallback checkpoint
            return self._present_seat_fallback_checkpoint()
        
        except Exception as e:
            self.audit.log_error(str(e), type(e).__name__)
            return False
    
    def _present_seat_fallback_checkpoint(self) -> bool:
        """Present checkpoint 3: Seat fallback selection"""
        checkpoint = Checkpoint(
            checkpoint_id=str(uuid.uuid4()),
            checkpoint_type=CheckpointType.SEAT_FALLBACK,
            title="Seat Assignment",
            description="Preferred seat unavailable, using auto-assignment",
            reasoning=self.reasoning.explain_checkpoint('SEAT_FALLBACK', {}),
            what_changed="Preferred seat not available, system will auto-assign",
            cli_command=f"atlas-flight booking seat --booking-id {self.booking_id} --preference auto --json",
            context={'booking_id': self.booking_id}
        )
        
        self.current_checkpoint = checkpoint
        self.checkpoints.append(checkpoint)
        self.state = BookingState.CHECKPOINT_3_PENDING
        
        self.audit.log_checkpoint_presented(
            checkpoint_id=checkpoint.checkpoint_id,
            checkpoint_type=checkpoint.checkpoint_type.value,
            reasoning=checkpoint.reasoning,
            cli_command=checkpoint.cli_command
        )
        
        return True
    
    def _create_order(self) -> bool:
        """Create the order (no checkpoint needed)"""
        try:
            # Note: passenger_details should be provided by the user
            # For now, using placeholder
            passenger_details = {
                "passengers": [{
                    "title": "Mr",
                    "first_name": "John",
                    "last_name": "Doe",
                    "date_of_birth": "1990-01-01",
                    "email": "john.doe@example.com",
                    "phone": "+1234567890"
                }]
            }
            
            order_result = self.cli.order_create(self.booking_id, passenger_details)
            
            if order_result.is_success():
                self.order_id = order_result.get_data('order_id')
                self.payment_confirmation_id = order_result.get_data('payment_confirmation_id')
                
                self.audit.log_order_created(
                    self.order_id,
                    order_result.request_id
                )
                
                # Proceed to final payment checkpoint
                self.state = BookingState.PAYMENT_PENDING
                return self._present_final_payment_checkpoint()
            
            else:
                self.audit.log_error(
                    order_result.message,
                    order_result.code,
                    order_result.retryable,
                    order_result.request_id
                )
                return False
        
        except Exception as e:
            self.audit.log_error(str(e), type(e).__name__)
            return False
    
    def _present_final_payment_checkpoint(self) -> bool:
        """Present checkpoint 4: Final payment summary"""
        checkpoint = Checkpoint(
            checkpoint_id=str(uuid.uuid4()),
            checkpoint_type=CheckpointType.FINAL_PAYMENT,
            title="Final Payment",
            description=f"Pay {self.confirmed_price:.2f} USD from Atlas balance",
            reasoning=self.reasoning.explain_checkpoint(
                'FINAL_PAYMENT',
                {'total_amount': self.confirmed_price}
            ),
            what_changed="Ready to issue ticket",
            cli_command=f"atlas-flight order pay --order-id {self.order_id} --payment-confirmation-id {self.payment_confirmation_id} --json",
            context={
                'order_id': self.order_id,
                'amount': self.confirmed_price,
                'payment_confirmation_id': self.payment_confirmation_id
            }
        )
        
        self.current_checkpoint = checkpoint
        self.checkpoints.append(checkpoint)
        self.state = BookingState.CHECKPOINT_4_PENDING
        
        self.audit.log_checkpoint_presented(
            checkpoint_id=checkpoint.checkpoint_id,
            checkpoint_type=checkpoint.checkpoint_type.value,
            reasoning=checkpoint.reasoning,
            cli_command=checkpoint.cli_command
        )
        
        return True
    
    def _execute_payment(self) -> bool:
        """Execute payment and poll for ticket issuance"""
        try:
            pay_result = self.cli.order_pay(self.order_id, self.payment_confirmation_id)
            
            if pay_result.is_success():
                self.audit.log_payment_completed(
                    self.order_id,
                    self.confirmed_price,
                    'USD',
                    pay_result.get_data('transaction_id', ''),
                    pay_result.request_id
                )
                
                # Poll for ticket issuance (up to 120 seconds)
                return self._poll_for_ticket()
            
            else:
                self.audit.log_error(
                    pay_result.message,
                    pay_result.code,
                    pay_result.retryable,
                    pay_result.request_id
                )
                return False
        
        except Exception as e:
            self.audit.log_error(str(e), type(e).__name__)
            return False
    
    def _poll_for_ticket(self, timeout: int = 120) -> bool:
        """Poll order status until ticket is issued"""
        import time
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                status_result = self.cli.order_status(self.order_id)
                
                if status_result.is_success():
                    status = status_result.get_data('status')
                    
                    if status == 'ticketed':
                        self.ticket_number = status_result.get_data('ticket_number')
                        self.state = BookingState.TICKET_ISSUED
                        
                        self.audit.log_ticket_issued(
                            self.order_id,
                            self.ticket_number,
                            status_result.request_id
                        )
                        
                        self.audit.log_session_completed(
                            True,
                            f"Ticket {self.ticket_number} issued successfully"
                        )
                        
                        self.state = BookingState.COMPLETE
                        return True
                    
                    elif status in ['failed', 'cancelled']:
                        self.state = BookingState.FAILED
                        self.audit.log_error(
                            f"Order status: {status}",
                            'ORDER_FAILED',
                            False
                        )
                        return False
                
                time.sleep(2)  # Poll every 2 seconds
            
            except Exception as e:
                self.audit.log_error(str(e), type(e).__name__)
                time.sleep(2)
        
        # Timeout
        self.audit.log_error(
            f"Ticket issuance timeout after {timeout}s",
            'TIMEOUT',
            False
        )
        return False
    
    def get_state(self) -> Dict[str, Any]:
        """Get current state summary"""
        return {
            'state': self.state.value,
            'checkpoints': [c.to_dict() for c in self.checkpoints],
            'current_checkpoint': self.current_checkpoint.to_dict() if self.current_checkpoint else None,
            'selected_option': self.selected_option.to_dict() if self.selected_option else None,
            'booking_id': self.booking_id,
            'order_id': self.order_id,
            'ticket_number': self.ticket_number,
            'original_price': self.original_price,
            'confirmed_price': self.confirmed_price
        }
