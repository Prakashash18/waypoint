"""
Atlas Flight CLI Wrapper
Subprocess execution layer for atlas-flight commands
"""

import subprocess
import json
import os
from typing import Optional, Dict, Any, List
from datetime import datetime
from .envelope import AtlasEnvelope, EnvelopeParser
from .errors import AtlasError, AuthError, SearchError, OfferError, BookingError, OrderError


class AtlasCLI:
    """Wrapper for atlas-flight CLI commands"""
    
    def __init__(self, timeout: int = 60):
        self.timeout = timeout
        self.parser = EnvelopeParser()
        
    def _execute(self, args: List[str]) -> AtlasEnvelope:
        """Execute atlas-flight command and return parsed envelope"""
        cmd = ['atlas-flight'] + args
        
        try:
            from ..agent.api_tracker import tracker
            import time
            start = time.time()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env={**os.environ, 'PATH': os.environ.get('PATH', '')}
            )
            duration_ms = int((time.time() - start) * 1000)
            
            # Extract command name for tracking
            endpoint = args[0] if args else "unknown"
            if len(args) > 1:
                endpoint += f" {args[1]}"
            
            if result.returncode != 0:
                from ..agent.api_tracker import tracker
                tracker.record_atlas_cli(
                    endpoint=endpoint,
                    duration_ms=duration_ms,
                    status="error",
                )
                raise AtlasError(
                    f"Command failed with exit code {result.returncode}",
                    stderr=result.stderr,
                    retryable=False
                )
            
            from ..agent.api_tracker import tracker as _tracker
            _tracker.record_atlas_cli(
                endpoint=endpoint,
                duration_ms=duration_ms,
            )
            return self.parser.parse(result.stdout)
            
        except subprocess.TimeoutExpired:
            from ..agent.api_tracker import tracker as _t
            _t.record_atlas_cli(
                endpoint=endpoint,
                status="error",
            )
            raise AtlasError(
                f"Command timed out after {self.timeout}s",
                retryable=True
            )
        except Exception as e:
            from ..agent.api_tracker import tracker as _t2
            _t2.record_atlas_cli(
                endpoint=endpoint,
                status="error",
            )
            raise AtlasError(
                f"Command execution failed: {str(e)}",
                retryable=False
            )
    
    # Auth commands
    def auth_login(self) -> AtlasEnvelope:
        """Login to Atlas"""
        return self._execute(['auth', 'login', '--json'])
    
    def auth_status(self) -> AtlasEnvelope:
        """Check authentication status"""
        return self._execute(['auth', 'status', '--json'])
    
    def auth_poll(self) -> AtlasEnvelope:
        """Poll for authentication completion"""
        return self._execute(['auth', 'poll', '--json'])
    
    # Search commands
    def search(
        self,
        origin: str,
        destination: str,
        depart: str,
        return_date: Optional[str] = None,
        adults: int = 1,
        children: int = 0,
        infants: int = 0,
        airlines: Optional[List[str]] = None,
        currency: str = 'USD',
        multiple_fare_families: bool = False
    ) -> AtlasEnvelope:
        """Search for flights"""
        args = [
            'search',
            '--origin', origin,
            '--destination', destination,
            '--depart', depart,
            '--adults', str(adults),
            '--children', str(children),
            '--infants', str(infants),
            '--currency', currency,
            '--json'
        ]
        
        if return_date:
            args.extend(['--return-date', return_date])
        
        if airlines:
            for airline in airlines:
                args.extend(['--airline', airline])
        
        if multiple_fare_families:
            args.append('--multiple-fare-families')
        
        return self._execute(args)
    
    # Offer commands
    def offer_list(self, search_id: str) -> AtlasEnvelope:
        """List available offers from a search"""
        return self._execute(['offer', 'list', '--search-id', search_id, '--json'])
    
    def offer_verify(self, offer_id: str) -> AtlasEnvelope:
        """Verify an offer is still available"""
        return self._execute(['offer', 'verify', '--offer-id', offer_id, '--json'])
    
    # Booking commands
    def booking_confirm_price(self, booking_id: str) -> AtlasEnvelope:
        """Confirm the price for a held booking.

        Takes the booking id from `offer verify`, not the offer id — the CLI
        has always wanted --booking-id, so this call could never have worked.
        """
        return self._execute(['booking', 'confirm-price',
                              '--booking-id', booking_id, '--json'])
    
    def booking_baggage_list(self, booking_id: str) -> AtlasEnvelope:
        """What baggage this fare offers, and what each piece costs."""
        return self._execute(['booking', 'baggage', 'list',
                              '--booking-id', booking_id, '--json'])

    def booking_baggage(self, booking_id: str, baggage_option: str) -> AtlasEnvelope:
        """Add baggage to booking"""
        return self._execute([
            'booking', 'baggage',
            '--booking-id', booking_id,
            '--option', baggage_option,
            '--json'
        ])
    
    def booking_seat(self, booking_id: str, seat_preference: str = 'auto') -> AtlasEnvelope:
        """Select seat for booking"""
        return self._execute([
            'booking', 'seat',
            '--booking-id', booking_id,
            '--preference', seat_preference,
            '--json'
        ])
    
    # Order commands
    def order_create(
        self,
        booking_id: str,
        passenger_details: Dict[str, Any]
    ) -> AtlasEnvelope:
        """Create an order"""
        # Convert passenger details to JSON string
        passenger_json = json.dumps(passenger_details)
        
        return self._execute([
            'order', 'create',
            '--booking-id', booking_id,
            '--passengers', passenger_json,
            '--json'
        ])
    
    def order_status(self, order_id: str) -> AtlasEnvelope:
        """Check order status"""
        return self._execute(['order', 'status', '--order-id', order_id, '--json'])
    
    def order_pay(self, order_id: str, payment_confirmation_id: str) -> AtlasEnvelope:
        """Pay for an order"""
        return self._execute([
            'order', 'pay',
            '--order-id', order_id,
            '--payment-confirmation-id', payment_confirmation_id,
            '--json'
        ])
    
    # Utility commands
    def doctor(self) -> AtlasEnvelope:
        """Run diagnostic checks"""
        return self._execute(['doctor', '--json'])
    
    def environment_use(self, env: str) -> AtlasEnvelope:
        """Switch environment (sandbox/production)"""
        return self._execute(['environment', 'use', env, '--json'])
